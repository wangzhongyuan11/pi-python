"""Managed Node extension host process (P15.5-T02).

Locates Node, prepares extension module roots (isolated dependency install),
boots ``node/extension-host/src/host.ts`` with type stripping, negotiates the
wire handshake, and exposes correlated request/response calls. The host is a
peer, not a shell escape: extension code never runs in the Python process.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path

from pi_coding_agent.rpc.framing import JsonlFramer, serialize_json_line

from .models import Hello, HelloAck, ProtocolError, Request, Response, parse_frame

HANDSHAKE_TIMEOUT = 30.0
REQUEST_TIMEOUT = 120.0
SHUTDOWN_TIMEOUT = 10.0


class NodeHostError(RuntimeError):
    """The managed Node host failed to start, negotiate, or answer."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class DependencyInstaller:
    """Prepare one extension module root; do nothing when there is nothing to install."""

    def install(self, module_root: Path) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class NpmInstaller(DependencyInstaller):
    """Run an isolated ``npm install --ignore-scripts`` for one module root."""

    def __init__(self, npm_executable: str = "npm") -> None:
        self._npm = npm_executable

    def install(self, module_root: Path) -> None:
        manifest = module_root / "package.json"
        if not manifest.exists() or (module_root / "node_modules").exists():
            return
        try:
            declared = json.loads(manifest.read_text(encoding="utf-8")).get("dependencies")
        except (json.JSONDecodeError, OSError):
            return
        if not isinstance(declared, dict) or not declared:
            return
        completed = subprocess.run(
            [self._npm, "install", "--ignore-scripts", "--no-audit", "--no-fund"],
            cwd=module_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
        if completed.returncode != 0:
            raise NodeHostError(
                f"dependency install failed for {module_root}: {completed.stderr.strip()[-500:]}"
            )


def find_node() -> str:
    node = shutil.which("node")
    if node is None:
        raise NodeHostError("node executable not found on PATH; Node host is unavailable")
    return node


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def host_entry(cwd: Path | None = None) -> Path:
    """Locate host.ts: env override, packaged copy, or the dev checkout."""

    override = os.environ.get("PI_PYTHON_NODE_HOST_DIR")
    candidates: tuple[Path, ...] = ()
    if override:
        candidates = (Path(override) / "src" / "host.ts",)
    else:
        candidates = (repository_root() / "node" / "extension-host" / "src" / "host.ts",)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise NodeHostError(f"node extension host entry not found: {candidates}")


class NodeHostProcess:
    """One supervised host process bound to one runtime generation."""

    def __init__(
        self,
        *,
        extensions: Sequence[str | Path],
        cwd: Path,
        generation: int = 0,
        state: Mapping[str, object] | None = None,
        installer: DependencyInstaller | None = None,
        node_executable: str | None = None,
        on_unexpected_exit: Callable[[str], None] | None = None,
    ) -> None:
        self._extensions = [Path(item) for item in extensions]
        self._cwd = Path(cwd)
        self._generation = generation
        self._state = dict(state or {})
        self._installer = installer
        self._node = node_executable or find_node()
        self._on_unexpected_exit = on_unexpected_exit
        self._process: asyncio.subprocess.Process | None = None
        self._framer = JsonlFramer()
        self._pending: dict[str, asyncio.Future[object]] = {}
        self._read_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._stderr_tail: list[str] = []
        self._ack: HelloAck | None = None
        self._request_handler: Callable[[str, Mapping[str, object]], Awaitable[object]] | None = (
            None
        )
        self._host_request_tasks: set[asyncio.Task[None]] = set()
        self._pending_commands: dict[str, str] = {}
        self._closed = False
        self._id = 0

    @property
    def ack(self) -> HelloAck:
        if self._ack is None:
            raise NodeHostError("handshake has not completed")
        return self._ack

    async def start(self) -> HelloAck:
        for extension in self._extensions:
            if self._installer is not None:
                module_root = _module_root(extension)
                if module_root is not None:
                    self._installer.install(module_root)
        config = {
            "extensions": [str(item) for item in self._extensions],
            "generation": self._generation,
        }
        config_path = self._cwd / f".node-host-config-{uuid.uuid4().hex}.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        entry = host_entry(self._cwd)
        try:
            self._process = await asyncio.create_subprocess_exec(
                self._node,
                "--experimental-strip-types",
                "--disable-warning=ExperimentalWarning",
                "--import",
                "./src/register.mjs",
                str(entry),
                "--config",
                str(config_path),
                cwd=str(entry.parent.parent),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as error:
            config_path.unlink(missing_ok=True)
            raise NodeHostError(f"failed to spawn node host: {error}") from error
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        hello = Hello(
            cwd=str(self._cwd),
            generation=self._generation,
            state=dict(self._state),
        )
        assert self._process.stdin is not None
        self._process.stdin.write(serialize_json_line(hello.model_dump()).encode("utf-8"))
        await self._process.stdin.drain()
        self._read_task = asyncio.create_task(self._read_loop())
        try:
            first = await asyncio.wait_for(self._wait_response("handshake"), HANDSHAKE_TIMEOUT)
        except TimeoutError as error:
            tail = self._stderr_tail_text()
            await self.close()
            raise NodeHostError(f"node host handshake timed out: {tail[:400]}") from error
        finally:
            config_path.unlink(missing_ok=True)
        if isinstance(first, HelloAck):
            self._ack = first
            return first
        raise NodeHostError("node host handshake produced an unexpected frame")

    async def _wait_response(self, request_id: str) -> object:
        future: asyncio.Future[object] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            return await future
        finally:
            self._pending.pop(request_id, None)

    async def _read_loop(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        while True:
            chunk = await self._process.stdout.read(8192)
            if not chunk:
                await self._fail_pending(f"node host exited\n{self._stderr_tail_text()}")
                if self._on_unexpected_exit is not None and not self._closed:
                    self._on_unexpected_exit(self._stderr_tail_text())
                return
            for line in self._framer.feed(chunk):
                if not line.strip():
                    continue
                try:
                    frame = parse_frame(line)
                except ProtocolError as error:
                    await self._fail_pending(error.args[0])
                    continue
                if isinstance(frame, HelloAck):
                    future = self._pending.pop("handshake", None)
                    if future and not future.done():
                        future.set_result(frame)
                elif isinstance(frame, Request):
                    task = asyncio.create_task(self._answer_host_request(frame))
                    self._host_request_tasks.add(task)
                    task.add_done_callback(self._host_request_tasks.discard)
                elif isinstance(frame, Response):
                    future = self._pending.get(frame.id)
                    self._pending_commands.pop(frame.id, None)
                    if future and not future.done():
                        if frame.ok:
                            future.set_result(frame.result)
                        else:
                            future.set_exception(
                                NodeHostError(
                                    frame.error or frame.error_code or "host request failed",
                                    code=frame.error_code,
                                )
                            )
                # Requests from the host are handled in T03/T04/T05.

    def set_request_handler(
        self, handler: Callable[[str, Mapping[str, object]], Awaitable[object]]
    ) -> None:
        """Answer host-initiated requests (registrations, actions, UI)."""

        self._request_handler = handler

    async def _answer_host_request(self, request: Request) -> None:
        if self._request_handler is None:
            self._send_response(
                Response.model_validate(
                    {
                        "id": request.id,
                        "ok": False,
                        "errorCode": "unknown_command",
                        "error": "python side has no host request handler",
                    }
                )
            )
            return
        try:
            result = await self._request_handler(request.command, request.payload)
        except Exception as error:  # noqa: BLE001 - errors cross the wire as strings
            self._send_response(
                Response.model_validate(
                    {
                        "id": request.id,
                        "ok": False,
                        "errorCode": "handler_error",
                        "error": str(error),
                    }
                )
            )
            return
        self._send_response(
            Response.model_validate({"id": request.id, "ok": True, "result": result})
        )

    def _send_response(self, response: Response) -> None:
        if self._process is None or self._process.stdin is None:
            return
        try:
            self._process.stdin.write(
                serialize_json_line(response.model_dump(by_alias=True)).encode("utf-8")
            )
        except (ConnectionResetError, RuntimeError):
            return

    async def _drain_stderr(self) -> None:
        assert self._process is not None and self._process.stderr is not None
        while True:
            chunk = await self._process.stderr.read(2048)
            if not chunk:
                return
            self._stderr_tail.extend(chunk.decode("utf-8", errors="replace").splitlines())
            del self._stderr_tail[:-400]

    def _stderr_tail_text(self) -> str:
        return "\n".join(self._stderr_tail[-10:])

    async def _fail_pending(self, message: str) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(NodeHostError(message))
        self._pending.clear()
        self._pending_commands.clear()

    async def request(self, command: str, payload: Mapping[str, object] | None = None) -> object:
        if self._closed or self._process is None or self._process.stdin is None:
            raise NodeHostError("node host is not running")
        self._id += 1
        request_id = f"py-{self._id}"
        request = Request(id=request_id, command=command, payload=dict(payload or {}))
        future: asyncio.Future[object] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        self._pending_commands[request_id] = command
        assert self._process.stdin is not None
        self._process.stdin.write(serialize_json_line(request.model_dump()).encode("utf-8"))
        try:
            await self._process.stdin.drain()
            return await asyncio.wait_for(future, REQUEST_TIMEOUT)
        except TimeoutError as error:
            raise NodeHostError(f"host request {command!r} timed out") from error

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        process = self._process
        stdin = process.stdin if process is not None else None
        if process is not None and stdin is not None and process.returncode is None:
            try:
                shutdown = Request(id="py-shutdown", command="shutdown", payload={})
                stdin.write(serialize_json_line(shutdown.model_dump()).encode("utf-8"))
                await stdin.drain()
            except (ConnectionResetError, RuntimeError):
                pass
        if self._process is not None:
            try:
                await asyncio.wait_for(self._process.wait(), SHUTDOWN_TIMEOUT)
            except TimeoutError:
                self._process.kill()
                await self._process.wait()
        if self._read_task is not None:
            self._read_task.cancel()
        if self._stderr_task is not None:
            self._stderr_task.cancel()
        await self._fail_pending("node host closed")

    @property
    def extensions(self) -> tuple[dict[str, object], ...]:
        return self.ack.extensions


def _module_root(extension: Path) -> Path | None:
    """The isolated install root for an extension's own runtime dependencies."""

    candidate = extension if extension.is_dir() else extension.parent
    if (candidate / "package.json").exists():
        return candidate
    return None


__all__ = [
    "DependencyInstaller",
    "HANDSHAKE_TIMEOUT",
    "NpmInstaller",
    "NodeHostError",
    "NodeHostProcess",
    "find_node",
    "host_entry",
]
