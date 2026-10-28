import sqlite3
from contextlib import closing

from toolsmith import lexical, semantic
from toolsmith.result import unwrap
from toolsmith.scopes import Scope


def example() -> tuple[str, ...]:
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.row_factory = sqlite3.Row
        connection.execute(
            "CREATE TABLE approved_text(reference TEXT PRIMARY KEY,text TEXT,text_digest TEXT)"
        )
        unwrap(semantic.prepare_connection(connection))
        unwrap(lexical.initialize_index(connection))
        unwrap(semantic.initialize_index(connection))
        source = lexical.Source(
            "document:one", "A caller-owned document about liquidity.", "Example"
        )
        with connection:
            connection.execute(
                "INSERT INTO approved_text VALUES (:reference,:text,:text_digest)",
                {
                    "reference": source.reference,
                    "text": source.text,
                    "text_digest": semantic.fingerprint(source.text),
                },
            )
            unwrap(lexical.index_source(connection, source, expected_digest=None))
        result = unwrap(lexical.search(connection, "liquidity", Scope("approved_text")))
        return tuple(hit.reference for hit in result.hits)


if __name__ == "__main__":
    print(example())
