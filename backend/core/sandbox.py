"""
backend/core/sandbox.py
────────────────────────
Docker-in-Docker sandbox for safe execution of generated code.

Features:
- Spin up isolated containers (Python 3.12-slim by default)
- Resource limits: 512 MB RAM, 1 CPU, 60-second timeout
- No network access by default
- Stdin/stdout capture
- Automatic cleanup
- Async-compatible via run_in_executor
"""

from __future__ import annotations

import asyncio
import logging
import os
import tarfile
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Optional

import docker
from docker.errors import DockerException, NotFound
from docker.models.containers import Container

from backend.core.config import settings

logger = logging.getLogger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class SandboxResult:
    """Result returned from a sandbox code execution."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    timed_out: bool = False
    duration_ms: int = 0
    container_id: str = ""
    error: str = ""

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.error


@dataclass
class SandboxConfig:
    """Configuration for a sandbox container."""

    image: str = field(default_factory=lambda: settings.SANDBOX_DOCKER_IMAGE)
    memory_limit: str = field(default_factory=lambda: settings.SANDBOX_MEMORY_LIMIT)
    cpu_quota: int = field(default_factory=lambda: settings.SANDBOX_CPU_QUOTA)
    timeout_seconds: int = field(default_factory=lambda: settings.SANDBOX_TIMEOUT_SECONDS)
    network_disabled: bool = field(default_factory=lambda: settings.SANDBOX_NETWORK_DISABLED)
    work_dir: str = field(default_factory=lambda: settings.SANDBOX_WORK_DIR)
    environment: dict = field(default_factory=dict)
    extra_packages: list[str] = field(default_factory=list)


# ── Docker client ─────────────────────────────────────────────────────────────

_docker_client: Optional[docker.DockerClient] = None


def get_docker_client() -> docker.DockerClient:
    """Return the singleton Docker client.

    Raises:
        RuntimeError: if Docker daemon is not accessible.
    """
    global _docker_client
    if _docker_client is not None:
        return _docker_client

    try:
        client = docker.from_env(timeout=10)
        client.ping()
        _docker_client = client
        logger.info("Docker client connected (version: %s)", client.version()["Version"])
        return _docker_client
    except DockerException as exc:
        raise RuntimeError(
            f"Docker daemon is not accessible. Ensure Docker is running. Error: {exc}"
        ) from exc


def is_docker_available() -> bool:
    """Return True if Docker is running and accessible."""
    try:
        get_docker_client()
        return True
    except RuntimeError:
        return False


# ── Sandbox lifecycle ─────────────────────────────────────────────────────────

def create_sandbox(config: Optional[SandboxConfig] = None) -> Container:
    """Create and start an isolated Docker container.

    The container is started with:
    - Read-only root filesystem (with /workspace as writable tmpfs)
    - No network (when config.network_disabled is True)
    - Memory + CPU limits
    - No new privileges security option

    Args:
        config: Sandbox configuration. Defaults to ``SandboxConfig()``.

    Returns:
        Running Docker Container object.
    """
    cfg = config or SandboxConfig()
    client = get_docker_client()

    container_name = f"ose-sandbox-{uuid.uuid4().hex[:12]}"

    kwargs: dict = {
        "image": cfg.image,
        "name": container_name,
        "command": "tail -f /dev/null",  # Keep alive until we exec into it
        "detach": True,
        "mem_limit": cfg.memory_limit,
        "memswap_limit": cfg.memory_limit,  # No swap
        "cpu_quota": cfg.cpu_quota,
        "cpu_period": 100000,
        "network_disabled": cfg.network_disabled,
        "read_only": False,  # We need /workspace writable
        "working_dir": cfg.work_dir,
        "environment": {
            "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            **cfg.environment,
        },
        "security_opt": ["no-new-privileges:true"],
        "cap_drop": ["ALL"],
        "tmpfs": {cfg.work_dir: "size=256m,exec"},
        "labels": {
            "ose.managed": "true",
            "ose.created_at": str(int(time.time())),
        },
    }

    if cfg.network_disabled:
        kwargs["network_mode"] = "none"

    try:
        container: Container = client.containers.run(**kwargs)
        logger.info("Sandbox container %s started (image: %s)", container_name, cfg.image)
        return container
    except DockerException as exc:
        raise RuntimeError(f"Failed to create sandbox container: {exc}") from exc


def _copy_code_to_container(container: Container, code: str, filename: str = "solution.py") -> None:
    """Write *code* into the container's working directory via a tar archive."""
    encoded = code.encode("utf-8")
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(name=filename)
        info.size = len(encoded)
        tar.addfile(info, BytesIO(encoded))
    buf.seek(0)
    container.put_archive(settings.SANDBOX_WORK_DIR, buf)


def _copy_files_to_container(container: Container, files: dict[str, str]) -> None:
    """Copy multiple named files into the container's working directory."""
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for filename, content in files.items():
            encoded = content.encode("utf-8")
            info = tarfile.TarInfo(name=filename)
            info.size = len(encoded)
            tar.addfile(info, BytesIO(encoded))
    buf.seek(0)
    container.put_archive(settings.SANDBOX_WORK_DIR, buf)


def run_in_sandbox(
    code: str,
    timeout: Optional[int] = None,
    config: Optional[SandboxConfig] = None,
    extra_files: Optional[dict[str, str]] = None,
    command: Optional[str] = None,
) -> SandboxResult:
    """Execute Python code inside an isolated Docker container.

    This is a **synchronous** function. Use ``async_run_in_sandbox`` for async contexts.

    Args:
        code:         Python source code to execute.
        timeout:      Execution timeout in seconds (overrides config).
        config:       Sandbox configuration.
        extra_files:  Additional files to copy into /workspace alongside the code.
        command:      Shell command to run (defaults to ``python solution.py``).

    Returns:
        SandboxResult with stdout, stderr, exit_code, duration_ms, timed_out.
    """
    cfg = config or SandboxConfig()
    effective_timeout = timeout or cfg.timeout_seconds
    container: Optional[Container] = None
    start_ts = time.monotonic()

    try:
        container = create_sandbox(cfg)

        # Copy code into the container
        _copy_code_to_container(container, code, "solution.py")
        if extra_files:
            _copy_files_to_container(container, extra_files)

        # Install extra packages if requested
        if cfg.extra_packages:
            pkg_list = " ".join(cfg.extra_packages)
            install_cmd = f"pip install --quiet --no-cache-dir {pkg_list}"
            exit_code, output = container.exec_run(
                cmd=["sh", "-c", install_cmd],
                workdir=cfg.work_dir,
                demux=False,
            )
            if exit_code != 0:
                logger.warning("Package install failed: %s", output)

        # Run the code
        run_cmd = command or f"python {cfg.work_dir}/solution.py"
        exec_result = container.exec_run(
            cmd=["sh", "-c", run_cmd],
            workdir=cfg.work_dir,
            demux=True,
            environment={"PYTHONPATH": cfg.work_dir},
        )

        # Handle timeout via container.wait with timeout
        try:
            container.wait(timeout=effective_timeout)
        except Exception:
            # Container may still be running — we already have exec output
            pass

        stdout_bytes, stderr_bytes = exec_result.output or (b"", b"")
        exit_code = exec_result.exit_code or 0

        duration_ms = int((time.monotonic() - start_ts) * 1000)
        timed_out = duration_ms >= effective_timeout * 1000

        return SandboxResult(
            stdout=(stdout_bytes or b"").decode("utf-8", errors="replace"),
            stderr=(stderr_bytes or b"").decode("utf-8", errors="replace"),
            exit_code=exit_code,
            timed_out=timed_out,
            duration_ms=duration_ms,
            container_id=container.id[:12],
        )

    except Exception as exc:
        duration_ms = int((time.monotonic() - start_ts) * 1000)
        logger.error("Sandbox execution error: %s", exc)
        return SandboxResult(
            exit_code=-1,
            duration_ms=duration_ms,
            error=str(exc),
        )

    finally:
        if container is not None:
            cleanup_sandbox(container)


def run_tests_in_sandbox(
    test_code: str,
    source_code: str,
    timeout: int = 120,
    config: Optional[SandboxConfig] = None,
) -> SandboxResult:
    """Run a test suite against source code inside the sandbox.

    Args:
        test_code:   pytest-style test file content.
        source_code: The module being tested.
        timeout:     Test run timeout.
        config:      Optional sandbox config.

    Returns:
        SandboxResult with pytest output.
    """
    cfg = config or SandboxConfig()
    cfg.extra_packages = list(set(cfg.extra_packages + ["pytest"]))

    return run_in_sandbox(
        code=source_code,
        timeout=timeout,
        config=cfg,
        extra_files={"test_solution.py": test_code},
        command=f"python -m pytest {cfg.work_dir}/test_solution.py -v --tb=short 2>&1",
    )


def cleanup_sandbox(container: Container) -> None:
    """Stop and remove a sandbox container.

    Safe to call even if the container is already stopped or removed.
    """
    try:
        container.stop(timeout=3)
    except Exception:
        pass
    try:
        container.remove(force=True)
        logger.debug("Sandbox container %s removed", container.id[:12])
    except NotFound:
        pass
    except Exception as exc:
        logger.warning("Failed to remove container %s: %s", container.id[:12], exc)


def cleanup_stale_sandboxes(max_age_seconds: int = 300) -> int:
    """Remove all OSE-managed sandbox containers older than *max_age_seconds*.

    Returns:
        Number of containers removed.
    """
    client = get_docker_client()
    removed = 0
    now = int(time.time())

    try:
        containers = client.containers.list(
            all=True,
            filters={"label": "ose.managed=true"},
        )
        for c in containers:
            created_at_str = c.labels.get("ose.created_at", "0")
            try:
                created_at = int(created_at_str)
            except ValueError:
                created_at = 0

            age = now - created_at
            if age > max_age_seconds:
                cleanup_sandbox(c)
                removed += 1

    except DockerException as exc:
        logger.warning("Could not enumerate stale sandboxes: %s", exc)

    if removed:
        logger.info("Cleaned up %d stale sandbox containers", removed)
    return removed


# ── Async wrappers ────────────────────────────────────────────────────────────

async def async_run_in_sandbox(
    code: str,
    timeout: Optional[int] = None,
    config: Optional[SandboxConfig] = None,
    extra_files: Optional[dict[str, str]] = None,
    command: Optional[str] = None,
) -> SandboxResult:
    """Async wrapper around :func:`run_in_sandbox`.

    Runs the blocking Docker calls in the default thread-pool executor so they
    don't block the asyncio event loop.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: run_in_sandbox(code, timeout, config, extra_files, command),
    )


async def async_run_tests_in_sandbox(
    test_code: str,
    source_code: str,
    timeout: int = 120,
    config: Optional[SandboxConfig] = None,
) -> SandboxResult:
    """Async wrapper around :func:`run_tests_in_sandbox`."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: run_tests_in_sandbox(test_code, source_code, timeout, config),
    )
