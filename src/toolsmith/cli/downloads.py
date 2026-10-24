from dataclasses import dataclass
from pathlib import Path

from toolsmith.acquisition.batch import DownloadRequest, download_batch
from toolsmith.acquisition.budgets import BudgetPolicy
from toolsmith.acquisition.client import HttpPolicy
from toolsmith.acquisition.config import read_budget_policy, read_http_policy
from toolsmith.cli.parser import Arguments
from toolsmith.files import read_bytes
from toolsmith.result import ToolsmithError, boundary, unwrap
from toolsmith.validation import canonical_json, fields, parse_json, text


@dataclass(frozen=True)
class DownloadProfile:
    http: HttpPolicy
    budget: BudgetPolicy


def read_profiles(path: Path) -> dict[str, DownloadProfile]:
    supplied = parse_json(unwrap(read_bytes(path, 4 * 1024 * 1024)), 4 * 1024 * 1024)
    if not isinstance(supplied, dict) or not supplied:
        raise ToolsmithError("invalid_input", "Supply a nonempty profile-name/object map")
    profiles: dict[str, DownloadProfile] = {}
    for name, value in supplied.items():
        identity = text(name, 300, "Profile name")
        item = fields(value, {"http", "budget"})
        profiles[identity] = DownloadProfile(
            unwrap(read_http_policy(canonical_json(item["http"]))),
            unwrap(read_budget_policy(canonical_json(item["budget"]))),
        )
    return profiles


def read_requests(path: Path, profiles: dict[str, DownloadProfile]) -> tuple[DownloadRequest, ...]:
    supplied = parse_json(unwrap(read_bytes(path, 32 * 1024 * 1024)), 32 * 1024 * 1024)
    if not isinstance(supplied, list):
        raise ToolsmithError("invalid_input", "Supply a JSON array of download requests")
    requests: list[DownloadRequest] = []
    for value in supplied:
        item = fields(value, {"id", "url", "profile", "destination"})
        name = text(item["profile"], 300, "Profile name")
        if name not in profiles:
            raise ToolsmithError("invalid_input", "Download references an unknown approved profile")
        profile = profiles[name]
        requests.append(
            DownloadRequest(
                text(item["id"], 300, "Download id"),
                text(item["url"], 8192, "URL"),
                Path(text(item["destination"], 8192, "Destination")),
                profile.http,
                profile.budget,
            )
        )
    return tuple(requests)


@boundary
def execute_downloads(arguments: Arguments) -> object:
    if (
        arguments.profiles is None
        or arguments.requests is None
        or arguments.network_state is None
        or arguments.task is None
    ):
        raise ToolsmithError(
            "invalid_input", "Batch downloads require profiles, requests, network state and task"
        )
    profiles = read_profiles(arguments.profiles)
    requests = read_requests(arguments.requests, profiles)
    return unwrap(
        download_batch(
            requests,
            arguments.network_state,
            arguments.task,
            concurrency=arguments.concurrency,
            deadline_seconds=arguments.deadline_seconds,
        )
    )
