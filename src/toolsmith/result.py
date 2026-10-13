from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Literal

type ErrorCode = Literal[
    "invalid_input",
    "not_found",
    "conflict",
    "denied",
    "limit",
    "unavailable",
    "deferred",
    "integrity",
    "io",
    "http",
    "tls",
]


@dataclass(frozen=True)
class Failure:
    code: ErrorCode
    message: str
    retry_after_seconds: float | None = None


@dataclass(frozen=True)
class Success[Value]:
    value: Value


type Result[Value] = Success[Value] | Failure


class ToolsmithError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.failure = Failure(code, message, retry_after_seconds)


def boundary[**Parameters, Value](
    function: Callable[Parameters, Value],
) -> Callable[Parameters, Result[Value]]:
    @wraps(function)
    def checked(*args: Parameters.args, **kwargs: Parameters.kwargs) -> Result[Value]:
        try:
            return Success(function(*args, **kwargs))
        except ToolsmithError as error:
            return error.failure
        except OSError:
            return Failure("io", "The explicit filesystem or network operation failed")

    return checked


def unwrap[Value](result: Result[Value]) -> Value:
    if isinstance(result, Failure):
        raise ToolsmithError(result.code, result.message, result.retry_after_seconds)
    return result.value
