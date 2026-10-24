import base64
import json
import sys
from collections.abc import Sequence

from toolsmith.cli.commands import execute
from toolsmith.cli.parser import Arguments, make_parser
from toolsmith.files import absolute_path, write_new_bytes
from toolsmith.result import Failure, Success, ToolsmithError, unwrap
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
        if arguments.output is not None:
            absolute_path(arguments.output)
            if arguments.output.exists() or arguments.output.is_symlink():
                raise ToolsmithError(
                    "conflict", "Output file already exists; it was not overwritten"
                )
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
    if arguments.output is not None and code == 0:
        try:
            content = json.dumps(
                payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            ).encode("utf-8")
            unwrap(write_new_bytes(arguments.output, content))
            payload = {
                "ok": True,
                "result": {"output": str(arguments.output), "bytes": len(content)},
            }
        except ToolsmithError as error:
            payload = {"ok": False, "error": json_value(error.failure)}
            code = EXIT_CODES[error.failure.code]
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
