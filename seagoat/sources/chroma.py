import os
import platform
from pathlib import Path

import chromadb
import onnxruntime
from chromadb.api.types import DefaultEmbeddingFunction
from chromadb.config import Settings
from chromadb.utils import embedding_functions

from seagoat.cache import Cache
from seagoat.repository import Repository
from seagoat.result import Result
from seagoat.utils.config import get_config_values

MAXIMUM_VECTOR_DISTANCE = 1.5
COREML_PROVIDER = "CoreMLExecutionProvider"
CPU_PROVIDER = "CPUExecutionProvider"
DEFAULT_EMBEDDING_FUNCTION = "DefaultEmbeddingFunction"
APPLE_SILICON_EMBEDDING_FUNCTION = "ONNXMiniLM_L6_V2"
COREML_OPT_IN_ENVIRONMENT_VARIABLE = "SEAGOAT_ENABLE_COREML_EMBEDDINGS"


class CoreMLDefaultEmbeddingFunction(DefaultEmbeddingFunction):
    def __call__(self, input):
        embedding_function = getattr(
            embedding_functions, APPLE_SILICON_EMBEDDING_FUNCTION
        )
        return embedding_function(
            preferred_providers=[COREML_PROVIDER, CPU_PROVIDER]
        )(input)


def get_metadata_and_distance_from_chromadb_result(chromadb_results):
    return (
        list(
            zip(
                chromadb_results["metadatas"][0],
                chromadb_results["distances"][0],
            )
        )
        if chromadb_results["metadatas"] and chromadb_results["distances"]
        else None
    ) or []


def format_results(query_text: str, repository, chromadb_results):
    files = {}

    for metadata, distance in get_metadata_and_distance_from_chromadb_result(
        chromadb_results
    ):
        if distance > MAXIMUM_VECTOR_DISTANCE:
            break
        path = str(metadata["path"])
        line = int(metadata["line"])
        git_object_id = str(metadata["git_object_id"])
        full_path = Path(repository.path) / path

        if not full_path.exists():
            continue

        if not repository.is_up_to_date_git_object(path, git_object_id):
            continue

        gitfile = repository.get_file(path)

        if path not in files:
            files[path] = Result(query_text, gitfile)
        files[path].add_line(line, distance)

    return files.values()


def is_coreml_available_on_apple_silicon():
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        return False

    return COREML_PROVIDER in onnxruntime.get_available_providers()


def create_embedding_function(embedding_function_config):
    embedding_function_name = embedding_function_config["name"]
    embedding_function_kwargs = embedding_function_config["arguments"]

    if (
        embedding_function_name == DEFAULT_EMBEDDING_FUNCTION
        and not embedding_function_kwargs
        and os.environ.get(COREML_OPT_IN_ENVIRONMENT_VARIABLE) == "1"
        and is_coreml_available_on_apple_silicon()
    ):
        return CoreMLDefaultEmbeddingFunction()

    return getattr(embedding_functions, embedding_function_name)(
        **embedding_function_kwargs
    )


def initialize(repository: Repository):
    cache = Cache("chroma", Path(repository.path), {})
    config = get_config_values(Path(repository.path))

    chroma_client = chromadb.PersistentClient(
        path=str(cache.get_cache_folder()),
        settings=Settings(
            anonymized_telemetry=False,
        ),
    )
    embedding_function = create_embedding_function(
        config["server"]["chroma"]["embeddingFunction"]
    )
    chroma_collection = chroma_client.get_or_create_collection(
        name="code_data", embedding_function=embedding_function
    )

    batch_size = config["server"]["chroma"]["batchSize"]
    batch_buffer = {"ids": [], "documents": [], "metadatas": []}

    def _flush_batch():
        if not batch_buffer["ids"]:
            return
        chroma_collection.upsert(
            ids=batch_buffer["ids"],
            documents=batch_buffer["documents"],
            metadatas=batch_buffer["metadatas"],
        )
        batch_buffer["ids"].clear()
        batch_buffer["documents"].clear()
        batch_buffer["metadatas"].clear()

    def fetch(query_text: str, limit: int):
        # Slightly overfetch results as it will sorted using a different score later
        maximum_chunks_to_fetch = 100  # this should be plenty, especially because many times context could be included
        n_results = min((limit + 1) * 2, maximum_chunks_to_fetch)

        chromadb_results = chroma_collection.query(
            query_texts=[query_text],
            n_results=n_results,
        )

        return format_results(query_text, repository, chromadb_results)

    def cache_chunk(chunk):
        batch_buffer["ids"].append(chunk.chunk_id)
        batch_buffer["documents"].append(chunk.chunk)
        batch_buffer["metadatas"].append({
            "path": chunk.path,
            "line": chunk.codeline,
            "git_object_id": chunk.object_id,
        })
        if len(batch_buffer["ids"]) >= batch_size:
            _flush_batch()

    def cache_repo():
        # chromadb does not need any repo cache action
        pass

    return {
        "fetch": fetch,
        "cache_chunk": cache_chunk,
        "cache_repo": cache_repo,
        "flush_batch": _flush_batch,
    }
