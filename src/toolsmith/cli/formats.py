from toolsmith.acquisition.urls import resolve_urls
from toolsmith.archives import list_archive, read_archive_member
from toolsmith.cli.parser import Arguments
from toolsmith.compression import expand_gzip
from toolsmith.files import read_bytes, write_new_bytes
from toolsmith.readers.json import read_json
from toolsmith.result import ToolsmithError, boundary, unwrap
from toolsmith.validation import text


@boundary
def execute_formats(arguments: Arguments) -> object:
    if arguments.file is None:
        raise ToolsmithError("invalid_input", "Supply an explicit input file")
    if arguments.action == "archive.list":
        return unwrap(list_archive(arguments.file))
    if arguments.action == "url.resolve":
        if arguments.url is None:
            raise ToolsmithError("invalid_input", "Supply the explicit base URL")
        values = unwrap(read_json(unwrap(read_bytes(arguments.file, 32 * 1024 * 1024))))
        if not isinstance(values, list):
            raise ToolsmithError("invalid_input", "Supply a JSON array of link targets")
        return unwrap(
            resolve_urls(arguments.url, tuple(text(value, 8192, "Link target") for value in values))
        )
    if arguments.destination is None:
        raise ToolsmithError("invalid_input", "Supply an explicit new destination file")
    if arguments.destination.exists() or arguments.destination.is_symlink():
        raise ToolsmithError("conflict", "Destination already exists; it was not overwritten")
    if arguments.action == "archive.read":
        value = unwrap(
            read_archive_member(
                arguments.file,
                text(arguments.member, 8192, "Archive member"),
                arguments.maximum_bytes,
            )
        )
    elif arguments.action == "decompress.gzip":
        value = unwrap(
            expand_gzip(
                unwrap(read_bytes(arguments.file, 128 * 1024 * 1024)), arguments.maximum_bytes
            )
        )
    else:
        raise ToolsmithError("invalid_input", "Choose a current format operation")
    unwrap(write_new_bytes(arguments.destination, value))
    return {"bytes": len(value), "destination": str(arguments.destination)}
