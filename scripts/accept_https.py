import json
import tempfile
from pathlib import Path

from verify import require_limits

from toolsmith.acquisition.http import acquire_http
from toolsmith.acquisition.policy import SourcePolicy
from toolsmith.result import unwrap
from toolsmith.storage.database import initialize_store


def main() -> int:
    require_limits()
    with tempfile.TemporaryDirectory(prefix="toolsmith-https-") as directory:
        parent = Path(directory)
        root = parent / "store"
        unwrap(initialize_store(root, "acceptance"))
        result = unwrap(
            acquire_http(
                root,
                "acceptance",
                parent / "network",
                "https://example.com/",
                SourcePolicy(
                    "example-public",
                    ("example.com",),
                    "text_only",
                    maximum_response_bytes=65_536,
                    deadline_seconds=20,
                ),
                "public-example",
                item="example",
            )
        )
        assert result.document is not None and result.artifact is None
        assert result.requests == 1
        print(
            json.dumps(
                {
                    "approved_public_source": result.final_url,
                    "requests": result.requests,
                    "wire_bytes": result.wire_bytes,
                    "native_dns_tls_https": "passed",
                    "temporary_state_disposed": "on exit",
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
