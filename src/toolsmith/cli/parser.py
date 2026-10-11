import argparse
from pathlib import Path
from typing import Never

from toolsmith.result import ToolsmithError


class Arguments(argparse.Namespace):
    action: str = ""
    root: Path | None = None
    collection: str | None = None
    json: bool = False
    file: Path | None = None
    title: str | None = None
    item: str | None = None
    name: str | None = None
    media_type: str | None = None
    source_url: str | None = None
    request_id: str | None = None
    version: str | None = None
    query: str | None = None
    part: int = 1
    start: int = 0
    length: int = 1200
    limit: int = 20
    offset: int = 0
    maximum_bytes: int = 16 * 1024 * 1024
    destination: Path | None = None
    minimum_age: float = 86_400
    policy: Path | None = None
    network_state: Path | None = None
    url: str | None = None


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ToolsmithError(
            "invalid_input",
            "Invalid command arguments; use --help for the current command contract",
        )


def make_parser() -> Parser:
    parser = Parser(
        prog="toolsmith",
        description="Optional libraries and CLI tools. No services or helper processes.",
    )
    parser.add_argument("--root", type=Path, help="Explicit absolute private store directory")
    parser.add_argument("--collection", help="Exact collection identity bound to the store")
    parser.add_argument("--json", action="store_true", help="Compact structured result")
    families = parser.add_subparsers(dest="family", required=True)
    parser.add_argument("--version", action="version", version="toolsmith 0.1.0")
    capabilities = families.add_parser("capabilities")
    capabilities.set_defaults(action="capabilities")
    store = families.add_parser("store").add_subparsers(dest="command", required=True)
    for name in ("init", "inspect"):
        store.add_parser(name).set_defaults(action="store." + name)
    readers = families.add_parser("read").add_subparsers(dest="command", required=True)
    for name in ("text", "html", "feed"):
        command = readers.add_parser(name)
        command.set_defaults(action="read." + name)
        command.add_argument("file", type=Path)
        if name == "text":
            command.add_argument("--title", required=True)
        elif name == "html":
            command.add_argument("--title")
        else:
            command.add_argument("--source-url", required=True)
            command.add_argument("--limit", type=int, default=100)
    texts = families.add_parser("text").add_subparsers(dest="command", required=True)
    put = texts.add_parser("put")
    put.set_defaults(action="text.put")
    put.add_argument("file", type=Path, help="Document JSON with explicit parts")
    put.add_argument("--item", required=True)
    put.add_argument("--request-id", required=True)
    inspect = texts.add_parser("inspect")
    inspect.set_defaults(action="text.inspect")
    inspect.add_argument("version")
    listing = texts.add_parser("list")
    listing.set_defaults(action="text.list")
    listing.add_argument(
        "--item", help="Select all retained versions for one item instead of current items"
    )
    listing.add_argument("--limit", type=int, default=20)
    listing.add_argument("--offset", type=int, default=0)
    search = texts.add_parser("search")
    search.set_defaults(action="text.search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--offset", type=int, default=0)
    citation = texts.add_parser("cite")
    citation.set_defaults(action="text.cite")
    citation.add_argument("version")
    citation.add_argument("--part", type=int, default=1)
    citation.add_argument("--start", type=int, default=0)
    citation.add_argument("--length", type=int, default=1200)
    files = families.add_parser("file").add_subparsers(dest="command", required=True)
    put_file = files.add_parser("put")
    put_file.set_defaults(action="file.put")
    put_file.add_argument("file", type=Path)
    put_file.add_argument("--name", required=True)
    put_file.add_argument("--media-type", required=True)
    put_file.add_argument("--source-url")
    put_file.add_argument("--request-id", required=True)
    for name in ("inspect", "read", "export"):
        command = files.add_parser(name)
        command.set_defaults(action="file." + name)
        command.add_argument("version")
        if name == "export":
            command.add_argument("destination", type=Path)
    http = families.add_parser("http").add_subparsers(dest="command", required=True)
    for name in ("inspect-policy", "limits", "fetch", "resume"):
        command = http.add_parser(name)
        command.set_defaults(action="http." + name)
        command.add_argument("--policy", type=Path, required=True)
        if name != "inspect-policy":
            command.add_argument("--network-state", type=Path, required=True)
        if name in {"fetch", "resume"}:
            command.add_argument("--request-id", required=True)
        if name == "fetch":
            command.add_argument("url")
            command.add_argument("--item", help="Store selected HTML/plain text")
            command.add_argument("--name", help="Store original only when policy permits")
    operation = families.add_parser("operation")
    operation.set_defaults(action="operation")
    operation.add_argument("request_id")
    maintenance = families.add_parser("maintenance").add_subparsers(dest="command", required=True)
    for name in (
        "integrity",
        "rebuild-index",
        "cleanup-preview",
        "cleanup-apply",
        "backup",
        "restore",
    ):
        command = maintenance.add_parser(name)
        command.set_defaults(action="maintenance." + name)
        if name == "cleanup-preview":
            command.add_argument("--minimum-age", type=float, default=86_400)
        if name == "cleanup-apply":
            command.add_argument(
                "file", type=Path, help="Exact cleanup plan JSON, not a command-result envelope"
            )
        if name in {"backup", "restore"}:
            command.add_argument(
                "destination", type=Path, help="New private destination; never overwritten"
            )
            command.add_argument("--maximum-bytes", type=int, default=256 * 1024 * 1024)
    return parser
