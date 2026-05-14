"""
This module allows you to use seagoat as a library
"""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from itertools import chain
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Set

import nest_asyncio
from tqdm import tqdm
from typing_extensions import TypedDict

from seagoat.cache import Cache
from seagoat.gitfile import GitFile
from seagoat.repository import Repository
from seagoat.result import get_best_score
from seagoat.sources import chroma, ripgrep
from seagoat.utils.config import get_config_values

INDEXING_BATCH_SIZE = 64


def milliseconds(seconds: float) -> float:
    return round(seconds * 1000, 3)


def batched(items, batch_size: int):
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


class RepositoryData(TypedDict):
    last_analyzed_version_of_branch: Dict[str, str]
    required_commits: Set[str]
    commits_already_analyzed: Set[str]
    file_data: Dict[str, GitFile]
    sorted_files: List[str]
    chunks_already_analyzed: Set[str]
    chunks_not_yet_analyzed: Set[str]
    last_successful_index_chunk_ids: Set[str]
    last_successful_index_repo_hash: str | None


nest_asyncio.apply()


def should_continue_by_default():
    return True


class Engine:
    """
    A search engine for a code repository
    """

    def __init__(self, path: str):
        """
        Initializes the library
        """
        self.path = path
        self._results = []
        self.cache = Cache[RepositoryData](
            "cache",
            Path(path),
            {
                "last_analyzed_version_of_branch": {},
                "required_commits": set(),
                "commits_already_analyzed": set(),
                "file_data": {},
                "sorted_files": [],
                "chunks_already_analyzed": set(),
                "chunks_not_yet_analyzed": set(),
                "last_successful_index_chunk_ids": set(),
                "last_successful_index_repo_hash": None,
            },
        )
        self.cache.load()
        self._ensure_cache_defaults()
        self.repository = Repository(path)
        self.config = get_config_values(Path(path))
        self._pending_reindex_chunk_ids: Set[str] | None = None
        self._pending_reindex_repo_hash: str | None = None

        ripgrep_fetcher = ripgrep.initialize(self.repository)
        ripgrep_fetcher.setdefault("name", "ripgrep")
        chroma_fetcher = chroma.initialize(self.repository)
        chroma_fetcher.setdefault("name", "chroma")

        self._fetchers = {
            "async": [ripgrep_fetcher],
            "sync": [chroma_fetcher],
        }

    def _ensure_cache_defaults(self):
        self.cache.data.setdefault("chunks_already_analyzed", set())
        self.cache.data.setdefault("chunks_not_yet_analyzed", set())
        self.cache.data["chunks_already_analyzed"] = set(
            self.cache.data["chunks_already_analyzed"]
        )
        self.cache.data["chunks_not_yet_analyzed"] = set(
            self.cache.data["chunks_not_yet_analyzed"]
        )
        self.cache.data.setdefault(
            "last_successful_index_chunk_ids",
            set(self.cache.data["chunks_already_analyzed"]),
        )
        self.cache.data["last_successful_index_chunk_ids"] = set(
            self.cache.data["last_successful_index_chunk_ids"]
        )
        self.cache.data.setdefault("last_successful_index_repo_hash", None)

    def _clear_pending_reindex(self):
        self._pending_reindex_chunk_ids = None
        self._pending_reindex_repo_hash = None

    def has_pending_reindex(self):
        return self._pending_reindex_chunk_ids is not None

    def finalize_pending_reindex(self):
        if self._pending_reindex_chunk_ids is None:
            return False

        stale_chunk_ids = (
            self.cache.data["last_successful_index_chunk_ids"]
            - self._pending_reindex_chunk_ids
        )

        if stale_chunk_ids:
            for source in chain(*self._fetchers.values()):
                delete_chunks = source.get("delete_chunks")
                if delete_chunks is not None:
                    delete_chunks(stale_chunk_ids)

        self.cache.data["last_successful_index_chunk_ids"] = set(
            self._pending_reindex_chunk_ids
        )
        self.cache.data["last_successful_index_repo_hash"] = (
            self._pending_reindex_repo_hash
        )
        self.cache.data["chunks_already_analyzed"].intersection_update(
            self._pending_reindex_chunk_ids
        )
        self.cache.data["chunks_not_yet_analyzed"].intersection_update(
            self._pending_reindex_chunk_ids
        )
        self.cache.persist()
        self._clear_pending_reindex()
        return True

    def analyze_codebase(
        self, minimum_chunks_to_analyze=None, should_continue=should_continue_by_default
    ):
        self._clear_pending_reindex()
        self.repository.analyze_files()

        for fetcher in self._fetchers["async"] + self._fetchers["sync"]:
            if not should_continue():
                return None
            if fetcher["cache_repo"](should_continue=should_continue) is False:
                return None
            if not should_continue():
                return None

        remaining_chunks_to_process = self._create_vector_embeddings(
            minimum_chunks_to_analyze, should_continue
        )
        if remaining_chunks_to_process is None:
            self._clear_pending_reindex()
            return None

        if not remaining_chunks_to_process:
            self.finalize_pending_reindex()

        return remaining_chunks_to_process

    def benchmark_indexing(self, minimum_chunks_to_analyze=None):
        benchmark_started_at = time.perf_counter()
        timings = {
            "repoScanMilliseconds": 0.0,
            "sourceCacheMilliseconds": {},
            "vectorEmbeddingsMilliseconds": 0.0,
        }
        analyzed_before = len(self.cache.data["chunks_already_analyzed"])

        repo_scan_started_at = time.perf_counter()
        self.repository.analyze_files()
        timings["repoScanMilliseconds"] = milliseconds(
            time.perf_counter() - repo_scan_started_at
        )

        for fetcher in self._fetchers["async"] + self._fetchers["sync"]:
            source_name = fetcher["name"]
            source_started_at = time.perf_counter()
            fetcher["cache_repo"]()
            timings["sourceCacheMilliseconds"][source_name] = milliseconds(
                time.perf_counter() - source_started_at
            )

        embeddings_started_at = time.perf_counter()
        remaining_chunks = self._create_vector_embeddings(minimum_chunks_to_analyze)
        self._clear_pending_reindex()
        timings["vectorEmbeddingsMilliseconds"] = milliseconds(
            time.perf_counter() - embeddings_started_at
        )
        timings["totalMilliseconds"] = milliseconds(
            time.perf_counter() - benchmark_started_at
        )

        analyzed_after = len(self.cache.data["chunks_already_analyzed"])
        return {
            "minimumChunksToAnalyze": minimum_chunks_to_analyze,
            "chunks": {
                "analyzedBefore": analyzed_before,
                "analyzedAfter": analyzed_after,
                "analyzedThisRun": analyzed_after - analyzed_before,
                "remaining": len(remaining_chunks or []),
            },
            "timings": timings,
        }

    def _add_to_collection(self, chunk):
        for source in chain(*self._fetchers.values()):
            source["cache_chunk"](chunk)

    def _add_chunks_to_collection(self, chunks):
        for source in chain(*self._fetchers.values()):
            if "cache_chunks" in source:
                source["cache_chunks"](chunks)
                continue
            for chunk in chunks:
                source["cache_chunk"](chunk)

    def process_chunk(self, chunk):
        self.process_chunks([chunk])

    def process_chunks(self, chunks):
        chunks_to_process = [
            chunk
            for chunk in chunks
            if chunk.chunk_id not in self.cache.data["chunks_already_analyzed"]
        ]
        if not chunks_to_process:
            return

        self._add_chunks_to_collection(chunks_to_process)
        for chunk in chunks_to_process:
            self.cache.data["chunks_already_analyzed"].add(chunk.chunk_id)

            if chunk.chunk_id in self.cache.data["chunks_not_yet_analyzed"]:
                self.cache.data["chunks_not_yet_analyzed"].remove(chunk.chunk_id)
        self.cache.persist()

    def _create_vector_embeddings(
        self, minimum_chunks_to_analyze=None, should_continue=should_continue_by_default
    ):
        chunks_to_process = []
        current_chunk_ids = set()

        for file, _ in self.repository.top_files():
            if not should_continue():
                self._clear_pending_reindex()
                return None
            for chunk in file.get_chunks():
                current_chunk_ids.add(chunk.chunk_id)
                if chunk.chunk_id not in self.cache.data["chunks_already_analyzed"]:
                    chunks_to_process.append(chunk)
                    self.cache.data["chunks_not_yet_analyzed"].add(chunk.chunk_id)

        self._pending_reindex_chunk_ids = current_chunk_ids
        self._pending_reindex_repo_hash = self.repository.get_status_hash()

        if minimum_chunks_to_analyze is None:
            minimum_chunks_to_analyze = min(
                max(40, int(len(chunks_to_process) * 0.2)),
                len(chunks_to_process),
            )

        chunks_to_analyze = chunks_to_process[:minimum_chunks_to_analyze]
        chunks_to_process = chunks_to_process[minimum_chunks_to_analyze:]

        logging.info("Analyzing source code")
        with tqdm(
            total=len(chunks_to_analyze),
        ) as progress:
            for batch in batched(chunks_to_analyze, INDEXING_BATCH_SIZE):
                if not should_continue():
                    self._clear_pending_reindex()
                    return None
                self.process_chunks(batch)
                progress.update(len(batch))

        for source in chain(*self._fetchers.values()):
            if not should_continue():
                self._clear_pending_reindex()
                return None
            source.get("flush_batch", lambda: None)()

        return chunks_to_process

    async def query(
        self,
        query: str,
        limit_clue=50,
        context_above=0,
        context_below=0,
        include_performance=False,
    ):
        """
        limit_clue: a clue regarding how many results will be processed in the end

        Sources don't need to respect this value and it does not have an inherent
        direct effect on the number of results returned, but sources can use it as
        a rule of thumb.
        """
        query_started_at = time.perf_counter()
        performance = {
            "sources": {},
            "contextMilliseconds": 0.0,
            "formatMilliseconds": 0.0,
        }
        self._results = []
        if not self.repository.frecency_scores:
            self.repository.analyze_files()

        def timed_fetch(source):
            source_started_at = time.perf_counter()
            source_results = list(source["fetch"](query, limit_clue))
            return (
                source["name"],
                source_results,
                milliseconds(time.perf_counter() - source_started_at),
            )

        executor = ThreadPoolExecutor(max_workers=1)
        loop = asyncio.get_event_loop()
        async_tasks = [
            loop.run_in_executor(
                executor,
                partial(timed_fetch, source),
            )
            for source in self._fetchers["async"]
        ]

        for source in self._fetchers["sync"]:
            source_name, source_results, elapsed = timed_fetch(source)
            performance["sources"][source_name] = elapsed
            self._results.extend(source_results)

        results = await asyncio.gather(*async_tasks)

        for source_name, source_results, elapsed in results:
            performance["sources"][source_name] = elapsed
            self._results.extend(source_results)

        context_started_at = time.perf_counter()
        self._include_context_lines(context_above, context_below)
        performance["contextMilliseconds"] = milliseconds(
            time.perf_counter() - context_started_at
        )

        format_started_at = time.perf_counter()
        formatted_results = self._format_results(query, limit_clue)
        performance["formatMilliseconds"] = milliseconds(
            time.perf_counter() - format_started_at
        )
        performance["totalMilliseconds"] = milliseconds(
            time.perf_counter() - query_started_at
        )

        if include_performance:
            return formatted_results, performance

        return formatted_results

    def _include_context_lines(self, context_above: int, context_below: int):
        for result in self._results:
            result.add_context_lines(-context_above)
            result.add_context_lines(context_below)

    def query_sync(self, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.query(*args, **kwargs))

    def _get_normalization_function(
        self, values: Iterable[float], min_=None, max_=None
    ) -> Callable[[float], float]:
        if not values:
            return lambda x: 0

        max_value = max_ or max(values)
        min_value = min_ or min(values)

        def normalize(value: float) -> float:
            if max_value != min_value:
                return (value - min_value) / (max_value - min_value)

            return 1

        return normalize

    def _format_results(self, query: str, hard_count_limit: int = 1000):
        merged_results = {}

        for result_item in self._results:
            if result_item.gitfile.path not in merged_results:
                merged_results[result_item.gitfile.path] = result_item
                continue

            merged_results[result_item.gitfile.path].extend(result_item)

        results_to_sort = list(merged_results.values())

        scores = [get_best_score(x) for x in results_to_sort]

        if not scores:
            return []

        top_files = {
            path: 0.0 - position_score
            for path, position_score in self.repository.frecency_scores.items()
        }

        normalize_score = self._get_normalization_function(scores, min_=0.0)
        normalize_file_position = self._get_normalization_function(top_files.values())

        def get_file_position(path: str):
            normalized_path = Path(path).as_posix()

            if normalized_path not in top_files:
                return 0

            return top_files[normalized_path]

        return list(
            sorted(
                results_to_sort,
                key=lambda x: (
                    0.7 * normalize_score(get_best_score(x))
                    + 0.3 * normalize_file_position(get_file_position(x.gitfile.path))
                ),
            )
        )[:hard_count_limit]
