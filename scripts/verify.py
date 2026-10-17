import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require_limits() -> None:
    membership = next(
        (
            line.split(":", 2)[2]
            for line in Path("/proc/self/cgroup").read_text().splitlines()
            if line.startswith("0::")
        ),
        None,
    )
    if membership is None:
        raise RuntimeError("Verification requires cgroup v2 with explicit aggregate limits")
    directory = Path("/sys/fs/cgroup") / membership.lstrip("/")
    values = [
        (directory / name).read_text().strip()
        for name in ("memory.max", "memory.swap.max", "pids.max")
    ]
    if (
        values[0] == "max"
        or int(values[0]) > 8 * 1024**3
        or values[1] != "0"
        or values[2] == "max"
        or int(values[2]) > 256
    ):
        raise RuntimeError(
            "Run verification in a scope bounded to 8 GiB, no swap and at most 256 tasks"
        )


def command(arguments: list[str]) -> None:
    subprocess.run(arguments, cwd=ROOT, check=True)


def main() -> int:
    require_limits()
    binary = Path(sys.executable).parent
    command(
        [str(binary / "ruff"), "format", "--check", "src", "tests", "scripts", "hatch_build.py"]
    )
    command([str(binary / "ruff"), "check", "src", "tests", "scripts", "hatch_build.py"])
    command([str(binary / "mypy")])
    command([sys.executable, "-m", "build", "--no-isolation", "--wheel"])
    command([sys.executable, "-m", "build", "--no-isolation", "--sdist"])
    files = sorted((ROOT / "tests").glob("test_*.py"))
    workers = min(len(files), len(os.sched_getaffinity(0)))
    reports: list[dict[str, str | int | float]] = []
    with tempfile.TemporaryDirectory(prefix="toolsmith-verification-") as temporary:
        for offset in range(0, len(files), workers):
            running = []
            try:
                for path in files[offset : offset + workers]:
                    output = Path(temporary) / (path.stem + ".log")
                    handle = output.open("w")
                    started = time.monotonic()
                    try:
                        process = subprocess.Popen(
                            [
                                sys.executable,
                                "-m",
                                "pytest",
                                "-q",
                                "--basetemp",
                                str(Path(temporary) / path.stem),
                                str(path),
                            ],
                            cwd=ROOT,
                            stdout=handle,
                            stderr=subprocess.STDOUT,
                        )
                    except BaseException:
                        handle.close()
                        raise
                    running.append((path, process, handle, output, started))
                for path, process, handle, output, started in running:
                    result = process.wait(timeout=120)
                    handle.close()
                    print(output.read_text(), end="", flush=True)
                    reports.append(
                        {
                            "file": path.name,
                            "observed_seconds": round(time.monotonic() - started, 3),
                            "exit_code": result,
                        }
                    )
            finally:
                for _, process, handle, _, _ in reversed(running):
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=5)
                    handle.close()
        print(
            json.dumps(
                {"cores": len(os.sched_getaffinity(0)), "workers": workers, "files": reports},
                sort_keys=True,
            ),
            flush=True,
        )
        if any(report["exit_code"] != 0 for report in reports):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
