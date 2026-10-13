import ipaddress
import re
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from toolsmith.result import ToolsmithError
from toolsmith.validation import text

HOST = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?\Z"
)
SECRET = re.compile(
    r"(?:^|[_-])(?:token|secret|password|passwd|authorization|credential|api[_-]?key|access[_-]?key)(?:$|[_-])",
    re.I,
)


def hostname(value: object) -> str:
    selected = text(value, 253, "Host").lower()
    if not HOST.fullmatch(selected) or selected.endswith(
        (".localhost", ".local", ".internal", ".test", ".invalid")
    ):
        raise ToolsmithError("denied", "Only explicit public DNS host names are permitted")
    try:
        ipaddress.ip_address(selected)
    except ValueError:
        return selected
    raise ToolsmithError("denied", "IP-literal hosts are not permitted")


def canonical_url(value: object) -> str:
    selected = text(value, 8192, "URL")
    if (
        any(
            character.isspace() or ord(character) < 32 or ord(character) == 127
            for character in selected
        )
        or "\\" in selected
    ):
        raise ToolsmithError("denied", "URL contains ambiguous whitespace or controls")
    try:
        parts = urlsplit(selected)
        port = parts.port
    except ValueError as error:
        raise ToolsmithError("invalid_input", "URL components are invalid") from error
    if (
        parts.scheme != "https"
        or parts.username is not None
        or parts.password is not None
        or port not in {None, 443}
        or parts.fragment
        or "#" in selected
    ):
        raise ToolsmithError(
            "denied", "URLs require HTTPS port 443 without credentials or fragments"
        )
    host = hostname(parts.hostname)
    if parts.netloc.lower() not in {host, host + ":443"}:
        raise ToolsmithError("denied", "URL authority is ambiguous")
    try:
        parameters = parse_qsl(
            parts.query, keep_blank_values=True, max_num_fields=100, errors="strict"
        )
    except (ValueError, UnicodeError) as error:
        raise ToolsmithError("invalid_input", "URL query is invalid or too large") from error
    if any(SECRET.search(key) for key, _ in parameters):
        raise ToolsmithError("denied", "Secret-like URL query parameters are not accepted")
    return urlunsplit(("https", host, parts.path or "/", parts.query, ""))


def public_address(value: object) -> str:
    selected = text(value, 64, "Resolved address")
    try:
        address = ipaddress.ip_address(selected)
    except ValueError as error:
        raise ToolsmithError("denied", "DNS did not return an IP address") from error
    if (
        not address.is_global
        or address.is_multicast
        or address.is_unspecified
        or isinstance(address, ipaddress.IPv6Address)
        and (
            address.ipv4_mapped is not None
            or address.sixtofour is not None
            or address.teredo is not None
        )
    ):
        raise ToolsmithError("denied", "DNS results must all be public unicast addresses")
    return address.compressed
