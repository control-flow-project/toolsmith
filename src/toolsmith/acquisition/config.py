from toolsmith.acquisition.budgets import BudgetPolicy, validate_policy
from toolsmith.acquisition.client import HttpPolicy, validate_http_policy
from toolsmith.acquisition.urls import hostname
from toolsmith.result import ToolsmithError, boundary
from toolsmith.validation import fields, identity, integer, number, parse_json


@boundary
def read_http_policy(content: bytes) -> HttpPolicy:
    value = fields(
        parse_json(content, 65536),
        {"hosts"},
        {
            "maximum_response_bytes",
            "maximum_total_bytes",
            "maximum_requests",
            "maximum_redirects",
            "deadline_seconds",
        },
    )
    hosts = value["hosts"]
    if not isinstance(hosts, list) or not 1 <= len(hosts) <= 32:
        raise ToolsmithError("invalid_input", "HTTP policy needs a bounded explicit host list")
    defaults = HttpPolicy(tuple(hostname(host) for host in hosts))
    return validate_http_policy(
        HttpPolicy(
            defaults.hosts,
            integer(
                value.get("maximum_response_bytes", defaults.maximum_response_bytes),
                1,
                128 * 1024**2,
                "Response bytes",
            ),
            integer(
                value.get("maximum_total_bytes", defaults.maximum_total_bytes),
                1,
                64 * 1024**3,
                "Total bytes",
            ),
            integer(
                value.get("maximum_requests", defaults.maximum_requests), 1, 100, "Maximum requests"
            ),
            integer(
                value.get("maximum_redirects", defaults.maximum_redirects),
                0,
                10,
                "Maximum redirects",
            ),
            number(value.get("deadline_seconds", defaults.deadline_seconds), 0.1, 60, "Deadline"),
        )
    )


@boundary
def read_budget_policy(content: bytes) -> BudgetPolicy:
    value = fields(
        parse_json(content, 65536),
        {
            "group",
            "period_seconds",
            "group_requests",
            "group_bytes",
            "task_requests",
            "task_bytes",
        },
        {"minimum_interval_seconds", "definition"},
    )
    return validate_policy(
        BudgetPolicy(
            identity(value["group"]),
            number(value["period_seconds"], 1, 31 * 86400, "Period"),
            integer(value["group_requests"], 1, 10000, "Group requests"),
            integer(value["group_bytes"], 1, 64 * 1024**3, "Group bytes"),
            integer(value["task_requests"], 1, 10000, "Task requests"),
            integer(value["task_bytes"], 1, 64 * 1024**3, "Task bytes"),
            number(value.get("minimum_interval_seconds", 0), 0, 31 * 86400, "Interval"),
            identity(value.get("definition", "explicit-budget-v1")),
        )
    )
