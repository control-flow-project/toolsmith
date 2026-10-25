from dataclasses import replace
from pathlib import Path

import pytest
from conftest import ControlledClock

from toolsmith.acquisition.budget_import import BudgetSnapshot, GroupUsage, Usage, import_budget
from toolsmith.acquisition.budgets import boot_identity
from toolsmith.acquisition.client import HttpPolicy, validate_http_policy
from toolsmith.acquisition.config import read_http_policy
from toolsmith.acquisition.limits import budget_policy, inspect_limits, reserve, settle
from toolsmith.acquisition.policy import SourcePolicy, read_policy, validate_policy
from toolsmith.acquisition.urls import canonical_url, public_address
from toolsmith.result import Failure, ToolsmithError, unwrap
from toolsmith.validation import canonical_json


@pytest.mark.parametrize("kind", ["http", "source"])
@pytest.mark.parametrize("encoded", [False, True])
@pytest.mark.parametrize("hosts", [("example.com", "example.com"), ("example.com", "EXAMPLE.COM")])
def test_duplicate_approved_hosts_are_rejected_after_normalization(
    kind: str, encoded: bool, hosts: tuple[str, ...]
) -> None:
    if encoded:
        result = (
            read_http_policy(canonical_json({"hosts": hosts}))
            if kind == "http"
            else read_policy(
                canonical_json(
                    {"format": 1, "group": "source", "hosts": hosts, "retention": "text_only"}
                )
            )
        )
        assert isinstance(result, Failure) and result.code == "invalid_input"
    else:
        with pytest.raises(ToolsmithError) as rejected:
            if kind == "http":
                validate_http_policy(HttpPolicy(hosts))
            else:
                validate_policy(SourcePolicy("source", hosts, "text_only"))
        assert rejected.value.failure.code == "invalid_input"


@pytest.mark.parametrize("kind", ["http", "source"])
@pytest.mark.parametrize("encoded", [False, True])
def test_approved_hosts_have_one_sorted_canonical_representation(kind: str, encoded: bool) -> None:
    hosts = ("SECOND.example.com", "EXAMPLE.COM")
    checked: HttpPolicy | SourcePolicy
    if kind == "http":
        checked = (
            unwrap(read_http_policy(canonical_json({"hosts": hosts})))
            if encoded
            else validate_http_policy(HttpPolicy(hosts))
        )
    else:
        checked = (
            unwrap(
                read_policy(
                    canonical_json(
                        {"format": 1, "group": "source", "hosts": hosts, "retention": "text_only"}
                    )
                )
            )
            if encoded
            else validate_policy(SourcePolicy("source", hosts, "text_only"))
        )
    assert checked.hosts == ("example.com", "second.example.com")


def test_archive_http_limits_do_not_reintroduce_hidden_counter_ceilings(
    tmp_path: Path, clock: ControlledClock
) -> None:
    source = SourcePolicy(
        "large", ("example.com",), "text_only", window_requests=20_000, window_bytes=128 * 1024**3
    )
    policy = budget_policy(source)
    assert policy.task_requests == policy.task_bytes == 2**63 - 1
    snapshot = BudgetSnapshot(
        60,
        clock.wall(),
        clock.wall(),
        (GroupUsage("large", 10_001, 65 * 1024**3),),
        (Usage("http", 10_001, 65 * 1024**3),),
    )
    root = tmp_path / "large-quotas"
    unwrap(import_budget(root, (policy,), snapshot, clock=clock, boot=boot_identity()))
    reservation = reserve(root, source, clock)
    settle(root, source, clock, reservation, 10)
    current = unwrap(inspect_limits(root, source, clock=clock))
    assert current.requests == 10_002 and current.reserved_bytes == 65 * 1024**3 + 10
    http = validate_http_policy(HttpPolicy(("example.com",), maximum_total_bytes=2**63 - 1))
    assert http.maximum_total_bytes == 2**63 - 1


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/",
        "https://user:pass@example.com/",
        "https://example.com:444/",
        "https://127.0.0.1/",
        "https://[::1]/",
        "https://example.com/#",
        "https://example.com/?access_token=secret",
        "https://example.com/?api%5fkey=secret",
        "https://example.com/\nsecret",
        "https://example.com\\@other.com/",
        "https://example.local/",
        "https://éxample.com/",
    ],
)
def test_unsafe_urls_are_rejected(url: str) -> None:
    with pytest.raises(ToolsmithError):
        canonical_url(url)


def test_url_normalizes_only_authority_not_query_or_path() -> None:
    assert (
        canonical_url("https://EXAMPLE.com:443/a%2Fb?x=1&x=2")
        == "https://example.com/a%2Fb?x=1&x=2"
    )


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "0.0.0.0",
        "224.0.0.1",
        "::1",
        "::ffff:8.8.8.8",
        "2002:0808:0808::1",
        "192.0.2.1",
    ],
)
def test_nonpublic_and_transition_addresses_are_rejected(address: str) -> None:
    with pytest.raises(ToolsmithError):
        public_address(address)


def test_policy_has_one_validated_contract() -> None:
    policy = unwrap(
        read_policy(
            b'{"format":1,"group":"example","hosts":["example.com"],"retention":"text_only"}'
        )
    )
    assert policy.maximum_response_bytes == 1024 * 1024
    assert isinstance(
        read_policy(b'{"format":1,"group":"example","hosts":["example.com"],"retention":[]}'),
        Failure,
    )
    assert isinstance(
        read_policy(
            b'{"format":1,"format":1,"group":"example","hosts":["example.com"],"retention":"original"}'
        ),
        Failure,
    )
    with pytest.raises(ToolsmithError):
        validate_policy(replace(policy, window_bytes=1))


def test_shared_limits_and_crash_reservations_are_conservative(
    tmp_path: Path, clock: ControlledClock
) -> None:
    root = tmp_path / "network"
    policy = SourcePolicy(
        "same-source",
        ("example.com",),
        "original",
        maximum_response_bytes=100,
        window_bytes=200,
        window_requests=2,
    )
    first = reserve(root, policy, clock)
    assert unwrap(inspect_limits(root, policy, clock=clock)).reserved_bytes == 100
    settle(root, policy, clock, first, 20)
    reserve(root, policy, clock)
    status = unwrap(inspect_limits(root, policy, clock=clock))
    assert status.requests == 2 and status.reserved_bytes == 120
    with pytest.raises(ToolsmithError) as blocked:
        reserve(root, policy, clock)
    assert blocked.value.failure.code == "deferred"
    changed = inspect_limits(root, replace(policy, window_requests=3), clock=clock)
    assert isinstance(changed, Failure) and changed.code == "conflict"
    clock.advance(60)
    assert unwrap(inspect_limits(root, policy, clock=clock)).requests == 0
    reserve(root, policy, clock)


def test_spacing_cooldown_and_clock_rollback(tmp_path: Path, clock: ControlledClock) -> None:
    root = tmp_path / "network"
    policy = SourcePolicy("source", ("example.com",), "text_only", minimum_interval_seconds=2)
    reservation = reserve(root, policy, clock)
    settle(root, policy, clock, reservation, 20, 30)
    with pytest.raises(ToolsmithError) as blocked:
        reserve(root, policy, clock)
    assert blocked.value.failure.retry_after_seconds == 30
    clock.advance(-100)
    with pytest.raises(ToolsmithError) as backwards:
        reserve(root, policy, clock)
    assert backwards.value.failure.retry_after_seconds == 130
    clock.advance(131)
    reserve(root, policy, clock)


def test_unknown_cooldown_survives_other_responses_and_window_rollover(
    tmp_path: Path, clock: ControlledClock
) -> None:
    root = tmp_path / "network"
    policy = SourcePolicy("source", ("example.com",), "text_only")
    first = reserve(root, policy, clock)
    clock.advance(60)
    second = reserve(root, policy, clock)
    settle(root, policy, clock, first, 20, None)
    settle(root, policy, clock, second, 20, 30)
    clock.advance(7 * 86_400)
    assert unwrap(inspect_limits(root, policy, clock=clock)).next_request_at is None
    with pytest.raises(ToolsmithError) as blocked:
        reserve(root, policy, clock)
    assert blocked.value.failure.code == "deferred"
    assert blocked.value.failure.retry_after_seconds is None
