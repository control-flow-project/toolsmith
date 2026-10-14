import re
from typing import Literal

from toolsmith.result import ToolsmithError, boundary
from toolsmith.validation import text

type QueryMode = Literal["literal", "phrase", "fts5"]


@boundary
def compile_query(query: str, mode: QueryMode = "literal") -> str:
    selected = text(query, 2048, "Lexical query")
    if mode == "fts5":
        return selected
    if mode == "phrase":
        return '"' + selected.replace('"', '""') + '"'
    if mode != "literal":
        raise ToolsmithError("invalid_input", "Choose literal, phrase or explicit fts5 query mode")
    if selected.count('"') % 2:
        raise ToolsmithError("invalid_input", "Lexical phrase has an unmatched quote")
    tokens: list[str] = []
    for ordinal, region in enumerate(selected.split('"')):
        terms = re.findall(r"[^\W_]+", region, re.UNICODE)
        if ordinal % 2:
            if not terms:
                raise ToolsmithError("invalid_input", "Lexical phrases must contain terms")
            tokens.append('"' + " ".join(terms) + '"')
        else:
            tokens.extend('"' + term + '"' for term in terms)
    if not 1 <= len(tokens) <= 32:
        raise ToolsmithError("invalid_input", "Lexical queries require 1..32 terms or phrases")
    return " AND ".join(tokens)
