import logging
import math
import time

import orjson

from seagoat import __version__
from seagoat.queue.base_queue import LOW_PRIORITY, MEDIUM_PRIORITY, BaseQueue
from seagoat.engine import INDEXING_BATCH_SIZE, batched

SECONDS_BETWEEN_MAINTENANCE = 10


def calculate_accuracy(chunks_analyzed: int, total_chunks: int) -> int:
    if total_chunks == 0 or total_chunks - chunks_analyzed == 0:
        return 100

    progress = chunks_analyzed / total_chunks

    k = 10
    x_0 = 0.25

    f_x = 1 / (1 + math.exp(-k * (progress - x_0)))
    f_0 = 1 / (1 + math.exp(k * x_0))
    f_1 = 1 / (1 + math.exp(-k * (1 - x_0)))

    normalized_value = (f_x - f_0) / (f_1 - f_0)
    percentage_value = normalized_value * 100
    rounded_percentage_value = int(percentage_value)

    if percentage_value > 0 and rounded_percentage_value == 0:
        return 1

    return rounded_percentage_value


class TaskQueue(BaseQueue):
    def _get_context(self):
        context = super()._get_context()

        from seagoat.engine import Engine

        seagoat_engine = Engine(self.kwargs["repo_path"])
        context["seagoat_engine"] = seagoat_engine
        context["last_maintenance"] = None
        context["last_repo_state_hash"] = seagoat_engine.cache.data[
            "last_successful_index_repo_hash"
        ]
        context["pending_repo_state_hash"] = None
        return context

    def handle_maintenance(self, context):
        if (
            context["last_maintenance"] is not None
            and time.time() - context["last_maintenance"] < SECONDS_BETWEEN_MAINTENANCE
        ):
            return

        current_repo_state_hash = context["seagoat_engine"].repository.get_status_hash()

        # Do not re-analyze repo if nothing changed
        if context["last_repo_state_hash"] == current_repo_state_hash:
            return

        context["last_maintenance"] = time.time()

        if self._task_queue.qsize() > 0:
            return

        logging.info("Checking repository for new changes")
        remaining_chunks_to_analyze = context["seagoat_engine"].analyze_codebase(
            self.kwargs["minimum_chunks_to_analyze"],
            should_continue=lambda: self._task_queue.qsize() == 0,
        )

        if remaining_chunks_to_analyze is None:
            logging.info("Paused repository maintenance because tasks are waiting.")
            context["pending_repo_state_hash"] = None
            return

        if remaining_chunks_to_analyze:
            context["pending_repo_state_hash"] = current_repo_state_hash
            logging.info("Analyzed the minimum number of chunks needed to operate. ")
            logging.info(
                "Note, %s chunks need to be analyzed for optimum performance.",
                len(remaining_chunks_to_analyze),
            )

            remaining_chunk_batches = list(
                batched(remaining_chunks_to_analyze, INDEXING_BATCH_SIZE)
            )
            for task_index, chunks in enumerate(remaining_chunk_batches):
                priority = MEDIUM_PRIORITY + (
                    (LOW_PRIORITY - MEDIUM_PRIORITY)
                    / len(remaining_chunk_batches)
                    * task_index
                )
                self.enqueue(
                    "analyze_chunks",
                    chunks,
                    priority=priority,
                    wait_for_result=False,
                )
        else:
            context["pending_repo_state_hash"] = None
            context["last_repo_state_hash"] = context["seagoat_engine"].cache.data[
                "last_successful_index_repo_hash"
            ]
            logging.info("Analyzed all chunks!")

    def handle_analyze_chunk(self, context, chunk):
        self.handle_analyze_chunks(context, [chunk])

    def handle_analyze_chunks(self, context, chunks):
        logging.info("Note, %s tasks left in the queue.", self._task_queue.qsize())
        logging.info("Processing %s chunks...", len(chunks))
        context["seagoat_engine"].process_chunks(chunks)

        if self._task_queue.qsize() == 0:
            if (
                context["seagoat_engine"].has_pending_reindex()
                and context.get("pending_repo_state_hash") is not None
            ):
                context["seagoat_engine"].finalize_pending_reindex()
                context["last_repo_state_hash"] = context["seagoat_engine"].cache.data[
                    "last_successful_index_repo_hash"
                ]
                context["pending_repo_state_hash"] = None
            logging.info("Analyzed all chunks!")

    def handle_query(self, context, **kwargs):
        include_performance = bool(kwargs.get("include_performance"))
        queue_wait_seconds = float(kwargs.get("__queue_wait_seconds", 0.0))
        query_kwargs = {
            "limit_clue": kwargs["limit_clue"],
            "context_above": int(kwargs["context_above"]),
            "context_below": int(kwargs["context_below"]),
        }
        if include_performance:
            query_kwargs["include_performance"] = True

        query_result = context["seagoat_engine"].query_sync(
            kwargs["query"],
            **query_kwargs,
        )
        engine_performance = None
        if include_performance:
            results, engine_performance = query_result
        else:
            results = query_result

        serialization_started_at = time.perf_counter()
        formatted_results = [result.to_json() for result in results]
        serialization_milliseconds = round(
            (time.perf_counter() - serialization_started_at) * 1000,
            3,
        )

        response_data = {
            "results": formatted_results,
            "version": __version__,
        }
        if include_performance:
            queue_wait_milliseconds = round(queue_wait_seconds * 1000, 3)
            response_data["performance"] = {
                "queueWaitMilliseconds": queue_wait_milliseconds,
                "serializationMilliseconds": serialization_milliseconds,
                "totalMilliseconds": round(
                    queue_wait_milliseconds
                    + serialization_milliseconds
                    + engine_performance["totalMilliseconds"],
                    3,
                ),
                "engine": engine_performance,
            }

        serialized_results = orjson.dumps(response_data)

        return serialized_results

    def get_stats(self):
        if self._context is None:
            return {
                "queue": {"size": self._task_queue.qsize()},
                "chunks": {"analyzed": 0, "unanalyzed": 0},
                "accuracy": {"percentage": 100},
            }

        engine = self._context["seagoat_engine"]
        analyzed_count = len(engine.cache.data["chunks_already_analyzed"])
        unanalyzed_count = len(engine.cache.data["chunks_not_yet_analyzed"])
        total_chunks = analyzed_count + unanalyzed_count

        return {
            "queue": {
                "size": self._task_queue.qsize(),
            },
            "chunks": {
                "analyzed": analyzed_count,
                "unanalyzed": unanalyzed_count,
            },
            "accuracy": {
                "percentage": calculate_accuracy(analyzed_count, total_chunks),
            },
        }

    def handle_get_stats(self, context):
        return self.get_stats()
