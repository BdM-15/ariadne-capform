"""MinerU FastAPI subprocess lifecycle — autostart from app.py when enabled."""

from __future__ import annotations

import logging
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

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


@dataclass
class MineruController:
    endpoint: MineruEndpoint
    process: subprocess.Popen | None = None
    _started_by_us: bool = False

    @property
    def started_by_us(self) -> bool:
        return self._started_by_us

    def start(
        self,
        *,
        python_executable: str | None = None,
        popen: Callable[..., subprocess.Popen] = subprocess.Popen,
        port_check: Callable[[str, int], bool] = is_port_listening,
        wait: Callable[[MineruEndpoint], bool] = wait_for_mineru,
    ) -> bool:
        if port_check(self.endpoint.host, self.endpoint.port):
            self._started_by_us = False
            return True

        executable = python_executable or sys.executable
        cmd = [
            executable,
            "-m",
            "mineru.cli.fast_api",
            "--host",
            self.endpoint.host,
            "--port",
            str(self.endpoint.port),
        ]
        logger.debug("Starting MinerU FastAPI: %s", " ".join(cmd))
        self.process = popen(cmd)
        self._started_by_us = True
        ready = wait(self.endpoint)
        if not ready:
            logger.error("MinerU did not become ready at %s", self.endpoint.docs_url)
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


def build_controller_from_settings(settings: Settings) -> MineruController | None:
    if not settings.mineru_enabled:
        return None
    endpoint = parse_mineru_endpoint(settings.mineru_local_endpoint)
    return MineruController(endpoint=endpoint)