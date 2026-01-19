"""Core runner for mcra-core integration.

This module encapsulates the mechanics for invoking the mcra-core JAR from Python.
CLI flags are based on common Java CLI patterns and may need adjustment to match
the exact mcra-core release you include in the image.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

DEFAULT_JAR_ENV = "MCRA_CORE_JAR"
DEFAULT_JAVA_BIN_ENV = "JAVA_BIN"
DEFAULT_ARTIFACT_NAME = "mcra-core.jar"


class MCRACoreError(Exception):
    """Raised when mcra-core cannot be invoked successfully."""


@dataclass
class MCRACoreInvocation:
    """Result metadata for an mcra-core invocation."""

    command: List[str]
    stdout: str
    stderr: str
    output_dir: Path


def resolve_mcra_jar(jar_path: Optional[str] = None) -> Path:
    """Resolve the mcra-core JAR path from explicit arg, env, or default location.

    Search order:
    1) Explicit `jar_path` argument
    2) Environment variable `MCRA_CORE_JAR`
    3) Default package-local artifacts directory: tasks/mcra/artifacts/mcra-core.jar
    """
    if jar_path:
        candidate = Path(jar_path)
    elif os.getenv(DEFAULT_JAR_ENV):
        candidate = Path(os.environ[DEFAULT_JAR_ENV])
    else:
        candidate = Path(__file__).resolve().parent.parent / "artifacts" / DEFAULT_ARTIFACT_NAME

    if not candidate.exists():
        raise FileNotFoundError(f"mcra-core jar not found at {candidate}")
    return candidate


def ensure_java_available(java_bin: Optional[str] = None) -> str:
    """Verify that the Java binary is available and return its path."""
    java_bin = java_bin or os.environ.get(DEFAULT_JAVA_BIN_ENV, "java")
    try:
        # `java -version` writes to stderr; we only care about exit code here.
        subprocess.run([java_bin, "-version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError as exc:
        raise MCRACoreError(f"Java binary not found: {java_bin}") from exc
    except subprocess.CalledProcessError as exc:
        raise MCRACoreError(f"Java command failed: {java_bin} -version") from exc
    return java_bin


def build_mcra_command(
    java_bin: str,
    jar_path: Path,
    config_path: Optional[Path] = None,
    input_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    java_opts: Optional[Iterable[str]] = None,
    extra_args: Optional[Iterable[str]] = None,
) -> List[str]:
    """Construct the mcra-core command line.

    CLI flags may need to be updated to match the actual mcra-core release.
    """
    cmd: List[str] = [java_bin]
    if java_opts:
        cmd.extend(java_opts)
    cmd.extend(["-jar", str(jar_path)])

    if config_path:
        cmd.extend(["--config", str(config_path)])
    if input_path:
        cmd.extend(["--input", str(input_path)])
    if output_dir:
        cmd.extend(["--output", str(output_dir)])
    if extra_args:
        cmd.extend(list(extra_args))
    return cmd


def run_mcra_core(
    *,
    jar_path: Optional[str] = None,
    java_bin: Optional[str] = None,
    config_path: Optional[str] = None,
    input_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    java_opts: Optional[Iterable[str]] = None,
    extra_args: Optional[Iterable[str]] = None,
    timeout: Optional[int] = None,
) -> MCRACoreInvocation:
    """Run the mcra-core JAR and return invocation metadata.

    Raises:
        FileNotFoundError: If the JAR path cannot be resolved.
        MCRACoreError: If Java is missing or mcra-core exits non-zero.
    """
    resolved_java = ensure_java_available(java_bin)
    resolved_jar = resolve_mcra_jar(jar_path)

    # Prepare filesystem paths.
    config = Path(config_path) if config_path else None
    input_file = Path(input_path) if input_path else None
    output_dir_path = Path(output_dir) if output_dir else Path(
        tempfile.mkdtemp(prefix="mcra-output-")
    )
    output_dir_path.mkdir(parents=True, exist_ok=True)

    cmd = build_mcra_command(
        java_bin=resolved_java,
        jar_path=resolved_jar,
        config_path=config,
        input_path=input_file,
        output_dir=output_dir_path,
        java_opts=java_opts,
        extra_args=extra_args,
    )

    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise MCRACoreError(f"mcra-core timed out after {timeout}s") from exc
    except OSError as exc:
        raise MCRACoreError(f"Failed to start mcra-core: {exc}") from exc

    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        detail = stderr or stdout or f"exit code {result.returncode}"
        raise MCRACoreError(f"mcra-core failed: {detail}")

    return MCRACoreInvocation(
        command=cmd,
        stdout=result.stdout,
        stderr=result.stderr,
        output_dir=output_dir_path,
    )


def format_command(cmd: Iterable[str]) -> str:
    """Return a shell-escaped command string for logging."""
    return " ".join(shlex.quote(part) for part in cmd)


def run_mcra_cli(
    input_file: str,
    config_file: str,
    output_dir: str,
    *,
    mcra_bin: str = "mcra",
    extra_args: Optional[Iterable[str]] = None,
    timeout: Optional[int] = None,
    print_output: bool = True,
) -> subprocess.CompletedProcess:
    """Run the MCRA CLI executable (not the Java JAR) and return the process result."""
    if not shutil.which(mcra_bin):
        raise MCRACoreError(f"MCRA executable not found: {mcra_bin}")

    command = [
        mcra_bin,
        "--input",
        input_file,
        "--config",
        config_file,
        "--output",
        output_dir,
    ]
    if extra_args:
        command.extend(list(extra_args))

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )

    if print_output:
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)

    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        detail = stderr or stdout or f"exit code {result.returncode}"
        raise MCRACoreError(f"MCRA CLI failed: {detail}")

    return result
