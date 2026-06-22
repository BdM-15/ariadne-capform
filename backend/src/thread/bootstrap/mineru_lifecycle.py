"""MinerU FastAPI subprocess lifecycle — GPU sidecar from .venv-mineru."""

from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

from thread.bootstrap.mineru_paths import (
    mineru_api_executable,
    mineru_install_hint,
    mineru_installed,
    repo_root,
)
from thread.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MineruEndpoint:
    host: str
    port: int

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def docs_url(self) -> str:
        return f"{self.base_url}/docs"


def parse_mineru_endpoint(endpoint: str) -> MineruEndpoint:
    parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8888
    return MineruEndpoint(host=host, port=port)


def is_port_listening(
    host: str,
    port: int,
    *,
    timeout: float = 0.5,
    socket_factory: Callable[[], socket.socket] | None = None,
) -> bool:
    factory = socket_factory or (lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM))
    sock = factory()
    sock.settimeout(timeout)
    try:
        target_host = "127.0.0.1" if host in {"localhost", "0.0.0.0"} else host
        sock.connect((target_host, port))
        return True
    except OSError:
        return False
    finally:
        try:
            sock.close()
        except OSError:
            pass


def wait_for_mineru(
    endpoint: MineruEndpoint,
    *,
    timeout: float = 180.0,
    interval: float = 1.0,
    url_opener: Callable[[str, float], object] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> bool:
    opener = url_opener or (lambda url, to: urllib.request.urlopen(url, timeout=to))
    deadline = clock() + timeout
    while clock() < deadline:
        for path in ("/health", "/docs"):
            try:
                response = opener(f"{endpoint.base_url}{path}", 5.0)
                status = getattr(response, "status", None) or response.getcode()  # type: ignore[union-attr]
                close = getattr(response, "close", None)
                if callable(close):
                    close()
                if status == 200:
                    return True
            except (urllib.error.URLError, ConnectionError, OSError):
                pass
        sleep(interval)
    return False


def _mineru_output_root() -> Path:
    root = repo_root() / "output"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _mineru_child_env(settings: Settings) -> dict[str, str]:
    env = os.environ.copy()
    if settings.mineru_device_mode:
        env["MINERU_DEVICE_MODE"] = settings.mineru_device_mode
    if settings.mineru_cuda_visible_devices:
        env["CUDA_VISIBLE_DEVICES"] = settings.mineru_cuda_visible_devices
    if settings.mineru_hybrid_batch_ratio > 0:
        env["MINERU_HYBRID_BATCH_RATIO"] = str(settings.mineru_hybrid_batch_ratio)
    env["MINERU_API_OUTPUT_ROOT"] = str(_mineru_output_root())
    return env


@dataclass
class MineruController:
    settings: Settings
    endpoint: MineruEndpoint
    process: subprocess.Popen | None = None
    _started_by_us: bool = False
    _stderr_log: object | None = None
    last_error: str = ""

    @property
    def started_by_us(self) -> bool:
        return self._started_by_us

    def start(
        self,
        *,
        wait_ready: bool = True,
        popen: Callable[..., subprocess.Popen] = subprocess.Popen,
        port_check: Callable[[str, int], bool] = is_port_listening,
        wait: Callable[[MineruEndpoint], bool] | None = None,
    ) -> bool:
        self.last_error = ""
        if port_check(self.endpoint.host, self.endpoint.port):
            self._started_by_us = False
            return True

        api_exe = mineru_api_executable(self.settings)
        if api_exe is None or not mineru_installed(self.settings):
            self.last_error = (
                "MinerU GPU environment missing — "
                + mineru_install_hint(self.settings)
            )
            logger.error(self.last_error)
            return False

        cmd = [
            str(api_exe),
            "--host",
            self.endpoint.host,
            "--port",
            str(self.endpoint.port),
            "--enable-vlm-preload",
            "true" if self.settings.mineru_vlm_preload else "false",
        ]
        logger.debug("Starting MinerU FastAPI: %s", " ".join(cmd))
        log_path = _mineru_output_root() / "mineru-api.log"
        try:
            self._stderr_log = open(log_path, "a", encoding="utf-8")
            self.process = popen(
                cmd,
                env=_mineru_child_env(self.settings),
                cwd=str(repo_root()),
                stdout=subprocess.DEVNULL,
                stderr=self._stderr_log,
            )
        except OSError as exc:
            self.last_error = f"MinerU spawn failed: {exc}"
            logger.error(self.last_error)
            if self._stderr_log is not None:
                with suppress(Exception):
                    self._stderr_log.close()
                self._stderr_log = None
            return False

        self._started_by_us = True
        fail_window = float(self.settings.mineru_spawn_fail_seconds)
        deadline = time.monotonic() + fail_window
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                err = ""
                if self.process.stderr:
                    try:
                        err = self.process.stderr.read().decode("utf-8", errors="replace")[:500]
                    except OSError:
                        pass
                self.last_error = err.strip() or f"MinerU exited with code {self.process.returncode}"
                logger.error("MinerU failed to start: %s", self.last_error)
                self.stop()
                return False
            time.sleep(0.25)

        if not wait_ready:
            logger.debug("MinerU spawned in background at %s (readiness probe deferred)", self.endpoint.base_url)
            return True

        wait_fn = wait or (
            lambda ep: wait_for_mineru(
                ep,
                timeout=float(self.settings.mineru_startup_timeout_seconds),
            )
        )
        ready = wait_fn(self.endpoint)
        if not ready:
            self.last_error = (
                f"MinerU did not become ready at {self.endpoint.docs_url} "
                f"within {self.settings.mineru_startup_timeout_seconds}s"
            )
            logger.error(self.last_error)
            self.stop()
            return False
        logger.debug("MinerU ready at %s", self.endpoint.docs_url)
        return True

    def stop(self, *, terminate_timeout: float = 10.0) -> None:
        proc = self.process
        if proc is None or not self._started_by_us:
            return
        if proc.poll() is not None:
            self.process = None
            return
        logger.info("Stopping MinerU FastAPI (pid=%s)", proc.pid)
        try:
            proc.terminate()
            try:
                proc.wait(timeout=terminate_timeout)
            except subprocess.TimeoutExpired:
                logger.warning("MinerU did not terminate; killing pid=%s", proc.pid)
                proc.kill()
                proc.wait(timeout=5.0)
        finally:
            self.process = None
            if self._stderr_log is not None:
                with suppress(Exception):
                    self._stderr_log.close()
                self._stderr_log = None


def build_controller_from_settings(settings: Settings) -> MineruController | None:
    if not settings.mineru_enabled or not settings.mineru_autostart:
        return None
    endpoint = parse_mineru_endpoint(settings.mineru_local_endpoint)
    return MineruController(settings=settings, endpoint=endpoint)