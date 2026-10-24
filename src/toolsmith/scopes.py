import re
import sqlite3
from dataclasses import dataclass

from toolsmith.result import ToolsmithError
from toolsmith.sqlite import execute

REFERENCE_WHITESPACE = (
    " \t\n\v\f\r\x1c\x1d\x1e\x1f\x85\xa0\u1680\u2000\u2001\u2002\u2003"
    "\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"
)


@dataclass(frozen=True)
class Scope:
    relation: str
    schema: str = "main"
    reference: str = "reference"
    digest: str = "text_digest"


def identifier(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,127}", value) is None:
        raise ToolsmithError("invalid_input", "Scope identifiers must be explicit SQL identifiers")
    return '"' + value + '"'


def scope_query(connection: sqlite3.Connection, scope: Scope) -> str:
    if (
        not isinstance(scope, Scope)
        or not isinstance(scope.schema, str)
        or scope.schema not in {"main", "temp"}
    ):
        raise ToolsmithError("invalid_input", "Supply an explicit typed main/temp database scope")
    schema, relation, reference, checksum = (
        identifier(value) for value in (scope.schema, scope.relation, scope.reference, scope.digest)
    )
    columns = {row[1] for row in execute(connection, f"PRAGMA {schema}.table_info({relation})")}
    if scope.reference not in columns or scope.digest not in columns:
        raise ToolsmithError(
            "invalid_input",
            "Scope table/view must expose the selected reference and digest columns",
        )
    selected = (
        f"SELECT {reference} AS reference, {checksum} AS text_digest FROM {schema}.{relation}"
    )
    return selected


def temporary_relation(connection: sqlite3.Connection, name: str, selection: str) -> Scope:
    relation = identifier(name)
    definition = f"CREATE VIEW {relation} AS {selection}"
    existing = execute(
        connection, "SELECT type,sql FROM sqlite_temp_master WHERE name = ?", (name,)
    ).fetchone()
    if existing is None:
        execute(connection, f"CREATE TEMP VIEW {relation} AS {selection}")
    elif existing[0] != "view" or existing[1] != definition:
        raise ToolsmithError("conflict", "A different temporary relation owns the index scope name")
    return Scope(name, schema="temp")


@dataclass(frozen=True)
class Coverage:
    entries: int
    indexed: int
    missing: int
    stale: int
    largest_source_chunks: int
    chunks: int


def coverage(connection: sqlite3.Connection, selected: str, document: str) -> Coverage:
    row = execute(
        connection,
        "SELECT count(*), coalesce(sum(d.reference IS NOT NULL AND d.text_digest = s.text_digest),0), coalesce(sum(d.reference IS NULL),0), coalesce(sum(d.reference IS NOT NULL AND d.text_digest != s.text_digest),0), coalesce(max(CASE WHEN d.text_digest = s.text_digest THEN d.chunks ELSE 0 END),0), count(DISTINCT s.reference), coalesce(sum(CASE WHEN typeof(s.reference) != 'text' OR length(CAST(s.reference AS BLOB)) NOT BETWEEN 1 AND 200 OR typeof(s.text_digest) != 'text' OR length(s.text_digest) != 64 THEN 1 WHEN d.text_digest = s.text_digest THEN 0 WHEN s.text_digest GLOB '*[^0-9a-f]*' OR instr(s.reference,char(0)) OR s.reference GLOB ('*[' || char(1) || '-' || char(31) || char(127) || ']*') OR length(trim(s.reference,?))=0 THEN 1 ELSE 0 END),0), coalesce(sum(CASE WHEN d.text_digest=s.text_digest THEN d.chunks ELSE 0 END),0) FROM ("
        + selected
        + ") s LEFT JOIN "
        + identifier(document)
        + " d ON d.reference = s.reference",
        (REFERENCE_WHITESPACE,),
    ).fetchone()
    if row[0] != row[5] or row[6]:
        raise ToolsmithError(
            "invalid_input", "Scope requires unique valid references and lowercase SHA-256 digests"
        )
    return Coverage(int(row[0]), int(row[1]), int(row[2]), int(row[3]), int(row[4]), int(row[7]))
