from dataclasses import dataclass

from toolsmith.result import Result, ToolsmithError, boundary
from toolsmith.validation import fields, parse_json, text


@dataclass(frozen=True)
class SearchQuery:
    id: str
    text: str


@dataclass(frozen=True)
class QueryResult[Report]:
    id: str
    result: Result[Report]


@dataclass(frozen=True)
class SearchBatch[Report]:
    items: tuple[QueryResult[Report], ...]


def validate_queries(queries: tuple[SearchQuery, ...]) -> tuple[SearchQuery, ...]:
    if not isinstance(queries, tuple):
        raise ToolsmithError("invalid_input", "Supply a tuple of typed search queries")
    seen: set[str] = set()
    for query in queries:
        if not isinstance(query, SearchQuery):
            raise ToolsmithError("invalid_input", "Supply typed search queries")
        identity = text(query.id, 300, "Query id")
        text(query.text, 16_384, "Query text")
        if identity in seen:
            raise ToolsmithError("invalid_input", "Query ids must be unique")
        seen.add(identity)
    return queries


@boundary
def read_queries(content: bytes) -> tuple[SearchQuery, ...]:
    supplied = parse_json(content, 32 * 1024 * 1024)
    if not isinstance(supplied, list):
        raise ToolsmithError("invalid_input", "Supply a JSON array of query id/text objects")
    queries: list[SearchQuery] = []
    for value in supplied:
        item = fields(value, {"id", "text"})
        queries.append(
            SearchQuery(text(item["id"], 300, "Query id"), text(item["text"], 16_384, "Query text"))
        )
    return validate_queries(tuple(queries))
