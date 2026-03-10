#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SUPPORTED_PYTHON_MINORS = (12, 11, 10)
COMMAND_BY_MODE = {
    "export": "babeldoc-export-jobs",
    "apply": "babeldoc-apply-jobs",
}


class SkillError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve and run babeldoc-jobpack CLI commands for export/apply "
            "using an isolated skill-local virtualenv."
        )
    )
    parser.add_argument("mode", choices=tuple(COMMAND_BY_MODE.keys()))
    parser.add_argument(
        "--runtime-dir",
        help="Skill-local runtime venv directory. Default: <skill_dir>/.venv",
    )
    parser.add_argument(
        "--package-spec",
        default=os.environ.get("BABELDOC_JOBPACK_SPEC", "babeldoc-jobpack"),
        help="PyPI package spec to install in skill-local .venv. Default: babeldoc-jobpack",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Fail if command is missing instead of auto-installing.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resolved command without executing it.",
    )
    args, command_args = parser.parse_known_args()
    args.command_args = strip_remainder_delimiter(command_args)
    return args


def main() -> int:
    args = parse_args()
    if not is_valid_pypi_spec(args.package_spec):
        print(
            "error: --package-spec must be a PyPI requirement spec "
            "(for example: babeldoc-jobpack or babeldoc-jobpack==0.1.0). "
            "VCS/path/url specs are not allowed.",
            file=sys.stderr,
        )
        return 2
    executable_name = COMMAND_BY_MODE[args.mode]
    runtime_dir = resolve_runtime_dir(args.runtime_dir)

    try:
        executable = resolve_executable(
            executable_name=executable_name,
            runtime_dir=runtime_dir,
            package_spec=args.package_spec,
            skip_install=args.skip_install,
        )
    except SkillError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    full_command = [executable, *args.command_args]
    if args.dry_run:
        print(
            json.dumps(
                {
                    "mode": args.mode,
                    "executable": executable,
                    "command": full_command,
                    "runtime_dir": str(runtime_dir),
                    "package_spec": args.package_spec,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    completed = subprocess.run(full_command)
    return int(completed.returncode)


def strip_remainder_delimiter(items: list[str]) -> list[str]:
    if items and items[0] == "--":
        return items[1:]
    return items


def is_valid_pypi_spec(spec: str) -> bool:
    raw = spec.strip()
    if not raw:
        return False
    blocked = ("git+", "://", "/", "\\", "@")
    if any(token in raw for token in blocked):
        return False
    return bool(re.match(r"^[A-Za-z0-9_.-]+(\s*[<>=!~]{1,2}\s*[A-Za-z0-9.*+-]+)?$", raw))


def resolve_runtime_dir(raw: str | None) -> Path:
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parent.parent / ".venv"


def resolve_executable(
    *,
    executable_name: str,
    runtime_dir: Path,
    package_spec: str,
    skip_install: bool,
) -> str:
    venv_executable = runtime_executable_path(runtime_dir, executable_name)
    if venv_executable.exists():
        return str(venv_executable)

    if skip_install:
        raise SkillError(
            f"Missing command in skill runtime: {venv_executable}. "
            "Run without --skip-install once to bootstrap .venv."
        )

    python_in_venv = ensure_runtime_python(runtime_dir)
    install_jobpack_package(
        python_in_venv=python_in_venv,
        package_spec=package_spec,
        runtime_dir=runtime_dir,
    )
    venv_executable = runtime_executable_path(runtime_dir, executable_name)
    if not venv_executable.exists():
        raise SkillError(
            f"Installed package but cannot find executable '{executable_name}' in runtime."
        )
    return str(venv_executable)


def ensure_runtime_python(runtime_dir: Path) -> Path:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    python_in_venv = runtime_python_path(runtime_dir)
    if python_in_venv.exists():
        return python_in_venv

    interpreter = find_supported_python()
    if not interpreter:
        supported = ", ".join(f"3.{minor}" for minor in SUPPORTED_PYTHON_MINORS)
        raise SkillError(
            f"No supported Python interpreter found. Install one of: {supported}"
        )

    run_checked(
        [interpreter, "-m", "venv", str(runtime_dir)],
        f"create skill runtime venv at {runtime_dir}",
    )
    if not python_in_venv.exists():
        raise SkillError(f"Runtime venv creation failed: {runtime_dir}")
    return python_in_venv


def find_supported_python() -> str | None:
    checked: list[str] = []
    for candidate in (
        "python3.12",
        "python3.11",
        "python3.10",
        sys.executable,
        "python3",
    ):
        if not candidate:
            continue
        path = shutil.which(candidate) if "/" not in candidate else candidate
        if not path or path in checked:
            continue
        checked.append(path)
        minor = query_python_minor(path)
        if minor in SUPPORTED_PYTHON_MINORS:
            return path
    return None


def query_python_minor(interpreter: str) -> int | None:
    try:
        out = subprocess.check_output(
            [
                interpreter,
                "-c",
                "import sys; print(sys.version_info.major); print(sys.version_info.minor)",
            ],
            text=True,
        )
    except Exception:
        return None
    parts = [line.strip() for line in out.splitlines() if line.strip()]
    if len(parts) < 2:
        return None
    if parts[0] != "3":
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def install_jobpack_package(
    *,
    python_in_venv: Path,
    package_spec: str,
    runtime_dir: Path,
) -> None:
    spec_marker = runtime_dir / ".jobpack_spec"
    existing_spec = spec_marker.read_text(encoding="utf-8").strip() if spec_marker.exists() else ""
    export_cmd = runtime_executable_path(runtime_dir, COMMAND_BY_MODE["export"])
    apply_cmd = runtime_executable_path(runtime_dir, COMMAND_BY_MODE["apply"])
    if existing_spec == package_spec and export_cmd.exists() and apply_cmd.exists():
        return

    pip_cmd = [str(python_in_venv), "-m", "pip"]
    run_checked([*pip_cmd, "install", "--upgrade", "pip"], "upgrade pip in skill .venv")
    run_checked(
        [*pip_cmd, "install", "--upgrade", package_spec],
        f"install '{package_spec}' from PyPI into skill .venv",
    )
    spec_marker.write_text(f"{package_spec}\n", encoding="utf-8")


def run_checked(command: list[str], label: str) -> None:
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode == 0:
        return
    stderr = completed.stderr or ""
    stdout = completed.stdout or ""
    raw = (stderr if stderr.strip() else stdout).strip()
    tail = raw.splitlines()[-16:]
    joined = "\n".join(tail)
    hint = ""
    merged = f"{stdout}\n{stderr}"
    if "No matching distribution found" in merged or "Requires-Python" in merged:
        hint = (
            "\nHint: this is usually a Python-version or wheel-availability issue. "
            "Use Python 3.12/3.11 and confirm your pip index can access required wheels."
        )
    raise SkillError(f"Failed to {label}.\n{joined}{hint}")


def runtime_python_path(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def runtime_executable_path(venv_dir: Path, executable_name: str) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / f"{executable_name}.exe"
    return venv_dir / "bin" / executable_name


if __name__ == "__main__":
    raise SystemExit(main())
