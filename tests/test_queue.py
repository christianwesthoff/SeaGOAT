from time import perf_counter, sleep
from unittest.mock import Mock
import threading

import orjson
import pytest

from seagoat.queue.base_queue import BaseQueue
from seagoat.queue.task_queue import TaskQueue
from seagoat.repository import Repository


@pytest.fixture(name="create_task_queue")
def create_task_queue(repo):
    created_queues = []

    def _create_task_queue():
        task_queue = TaskQueue(repo_path=repo.working_dir, minimum_chunks_to_analyze=0)
        created_queues.append(task_queue)
        return task_queue

    yield _create_task_queue

    for task_queue in created_queues:
        task_queue.shutdown()


@pytest.mark.parametrize(
    "chunks_analyzed, unanalyzed, expected_accuracy",
    [
        (0, 0, 100),
        (1, 999999, 1),
        (1000, 0, 100),
        (0, 20, 0),
        (5, 150, 2),
        (50, 450, 11),
        (5, 15, 45),
        (10, 10, 91),
        (100, 100, 91),
        (100_000, 100_001, 91),
        (15, 5, 99),
        (150, 5, 99),
        (150_000, 5, 99),
    ],
)
def test_handle_get_stats(chunks_analyzed, unanalyzed, expected_accuracy):
    task_queue = TaskQueue.__new__(TaskQueue)
    context = {
        "seagoat_engine": Mock(),
    }

    context["seagoat_engine"].cache.data = {
        "chunks_already_analyzed": set(range(chunks_analyzed)),
        "chunks_not_yet_analyzed": set(range(unanalyzed)),
    }

    task_queue._context = context
    task_queue._task_queue = Mock()
    task_queue._task_queue.qsize.return_value = 0
    stats = task_queue.get_stats()

    assert stats["accuracy"]["percentage"] == expected_accuracy


def test_handle_query_includes_performance_when_requested():
    task_queue = TaskQueue.__new__(TaskQueue)
    result = Mock()
    result.to_json.return_value = {"path": "file.py"}
    engine = Mock()
    engine.query_sync.return_value = (
        [result],
        {
            "totalMilliseconds": 10.5,
            "sources": {
                "chroma": 7.0,
                "ripgrep": 2.0,
            },
            "formatMilliseconds": 1.5,
        },
    )

    payload = task_queue.handle_query(
        {"seagoat_engine": engine},
        query="Markdown",
        limit_clue=3,
        context_above=0,
        context_below=1,
        include_performance=True,
        __queue_wait_seconds=0.012,
    )

    data = orjson.loads(payload)
    assert data["results"] == [{"path": "file.py"}]
    assert data["performance"]["queueWaitMilliseconds"] == 12.0
    assert data["performance"]["engine"]["sources"] == {
        "chroma": 7.0,
        "ripgrep": 2.0,
    }
    assert data["performance"]["totalMilliseconds"] >= 12.0
    engine.query_sync.assert_called_once_with(
        "Markdown",
        limit_clue=3,
        context_above=0,
        context_below=1,
        include_performance=True,
    )


def test_query_can_run_while_another_worker_handles_maintenance():
    maintenance_started = threading.Event()
    release_maintenance = threading.Event()

    class QueueWithBlockingMaintenance(BaseQueue):
        def handle_maintenance(self, context):
            maintenance_started.set()
            release_maintenance.wait(timeout=5.0)

        def handle_query(self, context):
            return "query-result"

    task_queue = QueueWithBlockingMaintenance(worker_count=2)
    try:
        assert maintenance_started.wait(timeout=5.0)
        started_at = perf_counter()
        assert task_queue.enqueue("query") == "query-result"
        assert perf_counter() - started_at < 1.0
    finally:
        release_maintenance.set()
        task_queue.shutdown()


def test_maintenance_does_not_mark_repo_analyzed_when_interrupted():
    task_queue = TaskQueue.__new__(TaskQueue)
    task_queue.kwargs = {"minimum_chunks_to_analyze": 0}
    task_queue._task_queue = Mock()
    task_queue._task_queue.qsize.return_value = 0
    engine = Mock()
    engine.repository.get_status_hash.return_value = "repo-hash"
    engine.analyze_codebase.return_value = None
    context = {
        "seagoat_engine": engine,
        "last_maintenance": None,
        "last_repo_state_hash": None,
    }

    task_queue.handle_maintenance(context)

    engine.analyze_codebase.assert_called_once()
    assert context["last_repo_state_hash"] is None


def test_important_files_are_analyzed_first(create_task_queue, mocker, repo):
    enqueue = mocker.patch("seagoat.queue.task_queue.TaskQueue.enqueue")
    create_task_queue()
    sleep(2.0)
    repository = Repository(repo.working_dir)
    repository.analyze_files()
    order_of_files_analyzed = []
    for call in enqueue.mock_calls:
        chunks = call.args[1]
        if not isinstance(chunks, list):
            chunks = [chunks]
        for chunk in chunks:
            path = chunk.path
            if not order_of_files_analyzed or order_of_files_analyzed[-1] != path:
                order_of_files_analyzed.append(path)

    # due to sorting by file priority, chunks of the same file should
    # be grouped together
    assert len(set(order_of_files_analyzed)) == len(order_of_files_analyzed)

    # the exact order of files should also match the priority list
    assert [file.path for file, _ in repository.top_files()] == order_of_files_analyzed


def test_background_indexing_enqueues_chunk_batches(create_task_queue, mocker, repo):
    enqueue = mocker.patch("seagoat.queue.task_queue.TaskQueue.enqueue")
    create_task_queue()
    sleep(2.0)

    analyze_chunk_calls = [
        call for call in enqueue.mock_calls if call.args[0] == "analyze_chunks"
    ]

    assert analyze_chunk_calls
    assert all(isinstance(call.args[1], list) for call in analyze_chunk_calls)
