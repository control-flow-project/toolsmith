import hashlib
from pathlib import Path

from toolsmith.acquisition.client import fetch_http
from toolsmith.acquisition.config import read_budget_policy, read_http_policy
from toolsmith.acquisition.http import acquire_http, resume_http
from toolsmith.acquisition.limits import inspect_limits
from toolsmith.acquisition.policy import read_policy
from toolsmith.cli.indexes import execute_index
from toolsmith.cli.parser import Arguments
from toolsmith.files import copy_file, hash_file, read_bytes, write_new_bytes
from toolsmith.operations.backup import backup_store, restore_store
from toolsmith.operations.cleanup import (
    apply_cleanup,
    preview_cleanup,
    validate_cleanup_plan,
)
from toolsmith.operations.integrity import check_integrity, rebuild_index
from toolsmith.readers import read_feed, read_html, read_text
from toolsmith.readers.json import read_json
from toolsmith.readers.tables import TableFormat, decode_table, project_table
from toolsmith.result import Result, Success, ToolsmithError, unwrap
from toolsmith.retrieval import read_citation, search_text
from toolsmith.semantic import inspect_model
from toolsmith.semantic.store import (
    clear_text_index,
    index_text,
    inspect_text_index,
    search_semantic_text,
)
from toolsmith.storage.artifacts import export_file, inspect_file, put_file, read_file
from toolsmith.storage.database import initialize_store, inspect_store
from toolsmith.storage.migration import migrate_store
from toolsmith.storage.models import document_from_json
from toolsmith.storage.operations import operation_status
from toolsmith.storage.text import inspect_text, list_text, put_text
from toolsmith.validation import parse_json, text


def required_text(value: str | None, label: str) -> str:
    return text(value, 8192, label)


def required_path(value: Path | None) -> Path:
    if value is None:
        raise ToolsmithError("invalid_input", "This command requires an explicit absolute path")
    return value


def execute(arguments: Arguments) -> Result[object]:
    action = arguments.action
    if action == "capabilities":
        return Success(
            {
                "implemented": [
                    "text",
                    "html",
                    "rss-atom",
                    "local-text",
                    "private-files",
                    "lexical-search",
                    "exact-citations",
                    "approved-https",
                    "explicit-http-resume",
                    "backup-restore",
                    "integrity",
                    "index-rebuild",
                    "preview-cleanup",
                    "offline-minilm",
                    "semantic-search",
                    "streaming-files",
                    "tabular-readers",
                    "caller-owned-lexical-index",
                    "caller-owned-search-cli",
                    "semantic-metadata-status",
                    "independent-https-response",
                    "group-task-budgets",
                    "literal-passages",
                    "exact-file-archives",
                    "private-tree-operations",
                    "generic-json-journal",
                    "forward-quota-import",
                ],
                "http_dependency": "http extra, loaded only for actual HTTP acquisition",
                "excluded": [
                    "servers",
                    "daemons",
                    "helper-processes",
                    "threads",
                    "browser",
                    "pdf",
                    "ocr",
                    "skills",
                    "fleet-runtime",
                ],
                "semantic_dependency": "semantic extra; verified operator-supplied local assets, no download",
            }
        )
    if action.startswith("read."):
        content = unwrap(read_bytes(required_path(arguments.file), 32 * 1024 * 1024))
        if action == "read.text":
            return read_text(content, required_text(arguments.title, "Title"))
        if action == "read.html":
            if arguments.selection not in {"text", "article"}:
                raise ToolsmithError("invalid_input", "Choose text or article selection")
            return read_html(
                content,
                arguments.title,
                selection="article" if arguments.selection == "article" else "text",
            )
        if action == "read.feed":
            return read_feed(
                content, required_text(arguments.source_url, "Source URL"), arguments.limit
            )
        if action == "read.json":
            return read_json(content)
        if arguments.format not in {"csv", "zip-csv", "gzip-csv"}:
            raise ToolsmithError("invalid_input", "Choose an explicit CSV format")
        selected_format: TableFormat = (
            "zip-csv"
            if arguments.format == "zip-csv"
            else "gzip-csv"
            if arguments.format == "gzip-csv"
            else "csv"
        )
        filters: dict[str, str] = {}
        for supplied in arguments.filters or []:
            key, separator, value = supplied.partition("=")
            if not separator or key in filters:
                raise ToolsmithError("invalid_input", "Supply distinct COLUMN=VALUE filters")
            filters[key] = value
        return project_table(
            unwrap(decode_table(content, selected_format)),
            tuple(arguments.columns or []),
            filters,
            arguments.limit,
            header_row=arguments.header_row,
        )
    if action.startswith("filesystem."):
        source = required_path(arguments.file)
        return (
            hash_file(source, arguments.maximum_bytes)
            if action == "filesystem.hash"
            else copy_file(source, required_path(arguments.destination), arguments.maximum_bytes)
        )
    if action.startswith("search."):
        return execute_index(arguments)
    if action.startswith("http."):
        if action == "http.request":
            response = unwrap(
                fetch_http(
                    required_text(arguments.url, "URL"),
                    unwrap(
                        read_http_policy(unwrap(read_bytes(required_path(arguments.policy), 65536)))
                    ),
                    required_path(arguments.network_state),
                    unwrap(
                        read_budget_policy(
                            unwrap(read_bytes(required_path(arguments.budget_policy), 65536))
                        )
                    ),
                    required_text(arguments.task, "Task"),
                )
            )
            unwrap(write_new_bytes(required_path(arguments.destination), response.content))
            return Success(
                {
                    "final_url": response.final_url,
                    "media_type": response.media_type,
                    "content_bytes": len(response.content),
                    "sha256": hashlib.sha256(response.content).hexdigest(),
                    "requests": response.requests,
                    "wire_bytes": response.wire_bytes,
                    "received_at": response.received_at,
                }
            )
        policy = unwrap(read_policy(unwrap(read_bytes(required_path(arguments.policy), 65_536))))
        if action == "http.inspect-policy":
            return Success(policy)
        network = required_path(arguments.network_state)
        if action == "http.limits":
            return inspect_limits(network, policy)
        root = required_path(arguments.root)
        collection = required_text(arguments.collection, "Collection")
        request = required_text(arguments.request_id, "Request identity")
        if action == "http.fetch":
            return acquire_http(
                root,
                collection,
                network,
                required_text(arguments.url, "URL"),
                policy,
                request,
                item=arguments.item,
                name=arguments.name,
            )
        return resume_http(root, collection, network, policy, request)
    if action == "semantic.model-check":
        return inspect_model(required_path(arguments.model_directory))
    root = required_path(arguments.root)
    collection = required_text(arguments.collection, "Collection")
    if action == "store.init":
        return initialize_store(root, collection)
    if action == "store.inspect":
        return inspect_store(root, collection)
    if action == "semantic.status":
        return inspect_text_index(root, collection)
    if action == "semantic.clear":
        return clear_text_index(root, collection)
    if action == "semantic.index":
        return index_text(
            root, collection, required_path(arguments.model_directory), arguments.limit
        )
    if action == "semantic.search":
        return search_semantic_text(
            root,
            collection,
            required_text(arguments.query, "Query"),
            required_path(arguments.model_directory),
            arguments.limit,
            item=arguments.item,
        )
    if action == "text.put":
        document = document_from_json(
            parse_json(
                unwrap(read_bytes(required_path(arguments.file), 16 * 1024 * 1024)),
                16 * 1024 * 1024,
            )
        )
        return put_text(
            root,
            collection,
            required_text(arguments.item, "Item"),
            document,
            required_text(arguments.request_id, "Request identity"),
        )
    if action == "text.inspect":
        return inspect_text(root, collection, required_text(arguments.version, "Version"))
    if action == "text.list":
        return list_text(root, collection, arguments.limit, arguments.offset, item=arguments.item)
    if action == "text.search":
        return search_text(
            root,
            collection,
            required_text(arguments.query, "Query"),
            arguments.limit,
            arguments.offset,
        )
    if action == "text.cite":
        return read_citation(
            root,
            collection,
            required_text(arguments.version, "Version"),
            arguments.part,
            arguments.start,
            arguments.length,
        )
    if action == "file.put":
        return put_file(
            root,
            collection,
            unwrap(read_bytes(required_path(arguments.file))),
            required_text(arguments.name, "Name"),
            required_text(arguments.media_type, "Media type"),
            required_text(arguments.request_id, "Request identity"),
            source_url=arguments.source_url,
        )
    if action == "file.inspect":
        return inspect_file(root, collection, required_text(arguments.version, "Version"))
    if action == "file.read":
        return read_file(root, collection, required_text(arguments.version, "Version"))
    if action == "file.export":
        return export_file(
            root,
            collection,
            required_text(arguments.version, "Version"),
            required_path(arguments.destination),
        )
    if action == "operation":
        return operation_status(
            root, collection, required_text(arguments.request_id, "Request identity")
        )
    if action == "maintenance.integrity":
        return check_integrity(root, collection)
    if action == "maintenance.rebuild-index":
        return rebuild_index(root, collection)
    if action == "maintenance.cleanup-preview":
        return preview_cleanup(root, collection, arguments.minimum_age)
    if action == "maintenance.cleanup-apply":
        return apply_cleanup(
            root,
            collection,
            validate_cleanup_plan(
                parse_json(unwrap(read_bytes(required_path(arguments.file), 1024 * 1024)))
            ),
        )
    if action == "maintenance.backup":
        return backup_store(
            root, collection, required_path(arguments.destination), arguments.maximum_bytes
        )
    if action == "maintenance.restore":
        return restore_store(
            root, collection, required_path(arguments.destination), arguments.maximum_bytes
        )
    if action == "maintenance.migrate":
        return migrate_store(
            root, collection, required_path(arguments.destination), arguments.maximum_bytes
        )
    raise ToolsmithError(
        "invalid_input", "Unknown command; no legacy command aliases are supported"
    )
