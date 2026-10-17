from toolsmith.scopes import Scope
from toolsmith.semantic.assets import ModelInfo, inspect_model
from toolsmith.semantic.chunks import Encoder, encode_query, prepare_embedding
from toolsmith.semantic.index import (
    SCHEMA_SQL,
    Hit,
    IndexReport,
    SearchReport,
    check_index,
    clear_index,
    indexed_digest,
    initialize_index,
    invalidate_embedding,
    prepare_connection,
    publish_embedding,
    relocate_embedding,
    search_embeddings,
)
from toolsmith.semantic.migration import migrate_index
from toolsmith.semantic.model import MiniLM, load_model
from toolsmith.semantic.profile import PROFILE_ID, Prepared, Source, fingerprint
from toolsmith.semantic.status import (
    IndexCoverage,
    IndexState,
    indexed_scope,
    inspect_coverage,
    inspect_index,
    pending_references,
)

__all__ = [
    "SCHEMA_SQL",
    "PROFILE_ID",
    "Scope",
    "Encoder",
    "Hit",
    "IndexReport",
    "IndexState",
    "IndexCoverage",
    "MiniLM",
    "ModelInfo",
    "Prepared",
    "SearchReport",
    "Source",
    "check_index",
    "clear_index",
    "encode_query",
    "fingerprint",
    "indexed_digest",
    "initialize_index",
    "inspect_model",
    "inspect_index",
    "indexed_scope",
    "inspect_coverage",
    "invalidate_embedding",
    "prepare_connection",
    "load_model",
    "migrate_index",
    "prepare_embedding",
    "publish_embedding",
    "pending_references",
    "relocate_embedding",
    "search_embeddings",
]
