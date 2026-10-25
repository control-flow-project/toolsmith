from dataclasses import dataclass
from typing import Literal

from toolsmith.acquisition.urls import approved_hosts
from toolsmith.files import MAX_FILE_BYTES
from toolsmith.result import ToolsmithError, boundary
from toolsmith.validation import fields, identity, integer, json_value, number, parse_json


@dataclass(frozen=True)
class SourcePolicy:
    group: str
    hosts: tuple[str, ...]
    retention: Literal["text_only", "original"]
    maximum_response_bytes: int = 1024 * 1024
    maximum_requests: int = 5
    maximum_redirects: int = 3
    deadline_seconds: float = 30
    window_seconds: float = 60
    window_requests: int = 10
    window_bytes: int = 8 * 1024 * 1024
    minimum_interval_seconds: float = 0


def validate_policy(policy: SourcePolicy) -> SourcePolicy:
    if not isinstance(policy, SourcePolicy) or not isinstance(policy.hosts, tuple):
        raise ToolsmithError(
            "invalid_input", "Source policy must be a SourcePolicy with an explicit host tuple"
        )
    value = fields(
        json_value(policy),
        {
            "group",
            "hosts",
            "retention",
            "maximum_response_bytes",
            "maximum_requests",
            "maximum_redirects",
            "deadline_seconds",
            "window_seconds",
            "window_requests",
            "window_bytes",
            "minimum_interval_seconds",
        },
    )
    selected = approved_hosts(policy.hosts)
    if not isinstance(value["retention"], str) or value["retention"] not in {
        "text_only",
        "original",
    }:
        raise ToolsmithError("invalid_input", "Retention must be text_only or original")
    retention: Literal["text_only", "original"] = (
        "text_only" if value["retention"] == "text_only" else "original"
    )
    maximum_bytes = integer(
        value["maximum_response_bytes"], 1, MAX_FILE_BYTES, "Maximum response bytes"
    )
    window_bytes = integer(value["window_bytes"], maximum_bytes, 2**63 - 1, "Window bytes")
    return SourcePolicy(
        identity(value["group"], "Source group"),
        selected,
        retention,
        maximum_bytes,
        integer(value["maximum_requests"], 1, 100, "Maximum operation requests"),
        integer(value["maximum_redirects"], 0, 10, "Maximum redirects"),
        number(value["deadline_seconds"], 0.1, 60, "Deadline seconds"),
        number(value["window_seconds"], 1, 86_400, "Window seconds"),
        integer(value["window_requests"], 1, 2**63 - 1, "Window requests"),
        window_bytes,
        number(value["minimum_interval_seconds"], 0, 86_400, "Minimum interval"),
    )


@boundary
def read_policy(content: bytes) -> SourcePolicy:
    required = {"format", "group", "hosts", "retention"}
    optional = {
        "maximum_response_bytes",
        "maximum_requests",
        "maximum_redirects",
        "deadline_seconds",
        "window_seconds",
        "window_requests",
        "window_bytes",
        "minimum_interval_seconds",
    }
    value = fields(parse_json(content, 65_536), required, optional)
    if integer(value["format"], 1, 1, "Policy format") != 1:
        raise ToolsmithError("invalid_input", "Only policy format one is supported")
    hosts = value["hosts"]
    if not isinstance(hosts, list) or not all(isinstance(host, str) for host in hosts):
        raise ToolsmithError("invalid_input", "Hosts must be strings")
    defaults = SourcePolicy("source", ("example.com",), "text_only")
    policy = SourcePolicy(
        identity(value["group"], "Source group"),
        approved_hosts(tuple(hosts)),
        "original" if value["retention"] == "original" else "text_only",
        integer(
            value.get("maximum_response_bytes", defaults.maximum_response_bytes),
            1,
            MAX_FILE_BYTES,
            "Maximum response bytes",
        ),
        integer(
            value.get("maximum_requests", defaults.maximum_requests), 1, 100, "Maximum requests"
        ),
        integer(
            value.get("maximum_redirects", defaults.maximum_redirects), 0, 10, "Maximum redirects"
        ),
        number(value.get("deadline_seconds", defaults.deadline_seconds), 0.1, 60, "Deadline"),
        number(value.get("window_seconds", defaults.window_seconds), 1, 86_400, "Window seconds"),
        integer(
            value.get("window_requests", defaults.window_requests), 1, 2**63 - 1, "Window requests"
        ),
        integer(
            value.get("window_bytes", defaults.window_bytes),
            1,
            2**63 - 1,
            "Window bytes",
        ),
        number(
            value.get("minimum_interval_seconds", defaults.minimum_interval_seconds),
            0,
            86_400,
            "Minimum interval",
        ),
    )
    if not isinstance(value["retention"], str) or value["retention"] not in {
        "text_only",
        "original",
    }:
        raise ToolsmithError("invalid_input", "Retention must be text_only or original")
    return validate_policy(policy)
