import hashlib
from pathlib import Path

from toolsmith import lexical, semantic
from toolsmith.cli.parser import Arguments
from toolsmith.clock import SystemClock, utc_now
from toolsmith.files import file_stamp, read_bytes
from toolsmith.result import ToolsmithError, boundary, unwrap
from toolsmith.sqlite import open_database, transaction
from toolsmith.validation import fields, integer, parse_json, source_reference, text


def sources(path: Path) -> tuple[semantic.Source, ...]:
    content = parse_json(unwrap(read_bytes(path, 128 * 1024 * 1024)), 128 * 1024 * 1024)
    if not isinstance(content, list) or len(content) > 10000:
        raise ToolsmithError("invalid_input", "Supply a JSON array of at most 10000 sources")
    output: list[semantic.Source] = []
    for value in content:
        item = fields(value, {"reference", "text"}, {"language"})
        output.append(
            semantic.Source(
                text(item["reference"], 200, "Reference"),
                text(item["text"], 8 * 1024 * 1024, "Source text", allow_empty=True),
                text(item.get("language", "en"), 20, "Language"),
            )
        )
    if len({source.reference for source in output}) != len(output):
        raise ToolsmithError("invalid_input", "Source references must be unique")
    return tuple(output)


@boundary
def execute_index(arguments: Arguments) -> object:
    if arguments.database is None:
        raise ToolsmithError("invalid_input", "Search commands require an explicit --database")
    kind, action = arguments.action.split(".")[1:]
    write = action in {"init", "index", "delete"}
    with open_database(arguments.database, create=action == "init", write=write) as connection:
        if action == "init":
            return unwrap(
                lexical.initialize_index(connection)
                if kind == "lexical"
                else semantic.initialize_index(connection)
            )
        if action == "delete":
            if arguments.reference is None:
                raise ToolsmithError("invalid_input", "Deletion requires an exact source reference")
            return unwrap(
                lexical.invalidate_source(connection, arguments.reference)
                if kind == "lexical"
                else semantic.invalidate_embedding(connection, arguments.reference)
            )
        if action == "status":
            if arguments.references is None:
                raise ToolsmithError("invalid_input", "Metadata status requires --references")
            names = parse_json(
                unwrap(read_bytes(arguments.references, 32 * 1024 * 1024)), 32 * 1024 * 1024
            )
            if not isinstance(names, list) or len(names) > 100000:
                raise ToolsmithError(
                    "invalid_input", "Supply bounded source references, not source bodies"
                )
            selected_references = tuple(source_reference(name) for name in names)
            return unwrap(
                lexical.inspect_index(connection, selected_references)
                if kind == "lexical"
                else semantic.inspect_index(connection, selected_references)
            )
        if arguments.sources is None:
            raise ToolsmithError(
                "invalid_input", "Supply --sources with explicit canonical/authorized text"
            )
        input_stamp = unwrap(file_stamp(arguments.sources))
        supplied = sources(arguments.sources)
        if unwrap(file_stamp(arguments.sources)) != input_stamp:
            raise ToolsmithError("conflict", "Source input changed during its validated read")
        canonical = {source.reference: source.text for source in supplied}
        if action == "check":
            return unwrap(
                lexical.check_index(connection, canonical.get)
                if kind == "lexical"
                else semantic.check_index(connection, canonical.get)
            )
        references = tuple(canonical)
        if action == "query":
            query = text(arguments.query, 2048, "Query")
            if kind == "lexical":
                candidates = tuple(
                    lexical.Candidate(reference, hashlib.sha256(body.encode()).hexdigest())
                    for reference, body in canonical.items()
                )
                return unwrap(
                    lexical.search(
                        connection, query, candidates, arguments.limit, mode=arguments.mode
                    )
                )
            if arguments.model_directory is None:
                raise ToolsmithError(
                    "invalid_input", "Semantic search requires an explicit --model-directory"
                )
            with unwrap(semantic.load_model(arguments.model_directory)) as encoder:
                return unwrap(
                    semantic.search_embeddings(
                        connection,
                        unwrap(semantic.encode_query(query, encoder)),
                        tuple(
                            semantic.Candidate(source.reference, semantic.fingerprint(source.text))
                            for source in supplied
                        ),
                        arguments.limit,
                    )
                )
        maximum = integer(arguments.limit, 1, 1000, "Foreground indexing batch")
        before = (
            {
                entry.reference: entry.digest
                for entry in unwrap(lexical.inspect_index(connection, references))
            }
            if kind == "lexical"
            else {
                entry.reference: entry.digest
                for entry in unwrap(semantic.inspect_index(connection, references))
            }
        )
        pending = tuple(
            source
            for source in supplied
            if hashlib.sha256(source.text.encode()).hexdigest() != before[source.reference]
        )
        selected = pending[:maximum]
        indexed = 0
        if kind == "lexical":
            with transaction(connection, "toolsmith_cli_index", write=True):
                for source in selected:
                    indexed += unwrap(
                        lexical.index_source(
                            connection,
                            lexical.Source(source.reference, source.text),
                            expected_digest=before[source.reference],
                        )
                    )
        elif selected:
            if arguments.model_directory is None:
                raise ToolsmithError(
                    "invalid_input", "Semantic indexing requires an explicit --model-directory"
                )
            with unwrap(semantic.load_model(arguments.model_directory)) as encoder:
                for source in selected:
                    prepared = unwrap(semantic.prepare_embedding(source, encoder))
                    if unwrap(file_stamp(arguments.sources)) != input_stamp:
                        raise ToolsmithError(
                            "conflict", "Canonical source input changed while encoding"
                        )
                    indexed += unwrap(
                        semantic.publish_embedding(
                            connection,
                            prepared,
                            source,
                            utc_now(SystemClock()),
                            expected_digest=before[source.reference],
                        )
                    )
        return {
            "indexed": indexed,
            "unchanged": len(supplied) - len(pending),
            "remaining": len(pending) - len(selected),
        }
