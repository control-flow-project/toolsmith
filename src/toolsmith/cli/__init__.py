import base64
import json
import sys
from collections.abc import Sequence

from toolsmith.cli.commands import execute
from toolsmith.cli.parser import Arguments, make_parser
from toolsmith.result import Failure, Success, ToolsmithError
from toolsmith.validation import JsonValue, json_value

EXIT_CODES = {
    "invalid_input": 2,
    "not_found": 3,
    "conflict": 4,
    "denied": 5,
    "limit": 6,
    "unavailable": 7,
    "deferred": 8,
    "integrity": 9,
    "io": 10,
    "http": 11,
    "tls": 12,
}


def main(argv: Sequence[str] | None = None) -> int:
    supplied = list(sys.argv[1:] if argv is None else argv)
    arguments = Arguments()
    try:
        make_parser().parse_args(supplied, namespace=arguments)
        result = execute(arguments)
    except ToolsmithError as error:
        result = error.failure
    value: JsonValue
    if isinstance(result, Success):
        value = (
            {"base64": base64.b64encode(result.value).decode(), "bytes": len(result.value)}
            if isinstance(result.value, bytes)
            else json_value(result.value)
        )
        payload = {"ok": True, "result": value}
        code = 0
    else:
        failure: Failure = result
        payload = {"ok": False, "error": json_value(failure)}
        code = EXIT_CODES[failure.code]
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            indent=None if "--json" in supplied else 2,
            separators=(",", ":") if "--json" in supplied else None,
        )
    )
    return code
