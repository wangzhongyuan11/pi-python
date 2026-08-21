"""Process-wide isolation helpers used only by the pytest bootstrap."""

from __future__ import annotations

import os
import re
import socket
import subprocess
import tempfile
from collections.abc import Mapping, MutableMapping, Sequence
from ipaddress import ip_address
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

ALLOW_LIVE_PROVIDER_ENV = "PI_PYTHON_ALLOW_LIVE_PROVIDER_TESTS"
ALLOW_NETWORK_ENV = "PI_PYTHON_ALLOW_NETWORK_TESTS"
ISOLATION_MARKER_ENV = "PI_PYTHON_TEST_ISOLATED"
SUBPROCESS_GUARD_ENV = "PI_PYTHON_TEST_SUBPROCESS_GUARD"

_EXACT_SECRET_NAMES = {
    "AWS_ACCESS_KEY_ID",
    "AWS_CONFIG_FILE",
    "AWS_DEFAULT_PROFILE",
    "AWS_PROFILE",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SECURITY_TOKEN",
    "AWS_SESSION_TOKEN",
    "AWS_SHARED_CREDENTIALS_FILE",
    "AWS_WEB_IDENTITY_TOKEN_FILE",
    "AZURE_CLIENT_CERTIFICATE_PATH",
    "AZURE_CLIENT_ID",
    "AZURE_CLIENT_SECRET",
    "AZURE_FEDERATED_TOKEN_FILE",
    "AZURE_PASSWORD",
    "AZURE_TENANT_ID",
    "DEEPSEEK_API_KEY",
    "GH_TOKEN",
    "GITHUB_PAT",
    "GITHUB_TOKEN",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "OPENAI_API_KEY",
    "SSH_ASKPASS",
    "SSH_AUTH_SOCK",
}
_SECRET_SUFFIXES = (
    "_ACCESS_KEY",
    "_ACCESS_TOKEN",
    "_API_KEY",
    "_AUTH_TOKEN",
    "_CLIENT_SECRET",
    "_PASSWORD",
    "_PRIVATE_KEY",
    "_SECRET",
    "_SESSION_TOKEN",
    "_TOKEN",
)
_NETWORK_CLIENT_PATTERN = re.compile(
    r"\b(curl|wget|httpie?|nc|ncat|netcat|telnet|ftp|ssh|scp|sftp)(?:\.exe)?\b",
    re.IGNORECASE,
)
_WEB_COMMAND_PATTERN = re.compile(
    r"invoke-(webrequest|restmethod)|start-bitstransfer|system\.net\.webclient",
    re.IGNORECASE,
)
_URL_PATTERN = re.compile(r"https?://[^\s\"']+", re.IGNORECASE)
_GIT_NETWORK_COMMANDS = {"clone", "fetch", "ls-remote", "pull", "push"}


def explicit_opt_in(environ: Mapping[str, str], name: str) -> bool:
    return environ.get(name) == "1"


def clear_sensitive_environment(environ: MutableMapping[str, str]) -> None:
    for name in tuple(environ):
        upper_name = name.upper()
        if upper_name in _EXACT_SECRET_NAMES or upper_name.endswith(_SECRET_SUFFIXES):
            environ.pop(name, None)


def _ensure_loopback(address: object) -> None:
    if not isinstance(address, tuple) or not address:
        return

    tuple_address = cast(tuple[object, ...], address)
    host = tuple_address[0]
    if isinstance(host, bytes):
        host = host.decode("ascii", errors="strict")
    if not isinstance(host, str):
        raise RuntimeError("external network is disabled during tests")
    if not host or host.casefold() == "localhost":
        return

    try:
        if ip_address(host.partition("%")[0]).is_loopback:
            return
    except ValueError:
        pass
    raise RuntimeError(f"external network is disabled during tests: {host}")


class NetworkGuard:
    """Patch common Python socket entry points while allowing loopback traffic."""

    def __init__(self) -> None:
        self._patches: list[tuple[object, str, Any]] = []

    def _patch(self, owner: object, name: str, replacement: Any) -> None:
        self._patches.append((owner, name, getattr(owner, name)))
        setattr(owner, name, replacement)

    def install(self) -> None:
        if self._patches:
            return

        original_create_connection = socket.create_connection
        original_connect = socket.socket.connect
        original_connect_ex = socket.socket.connect_ex
        original_getaddrinfo = socket.getaddrinfo
        original_gethostbyaddr = socket.gethostbyaddr
        original_gethostbyname = socket.gethostbyname
        original_gethostbyname_ex = socket.gethostbyname_ex
        original_getnameinfo = socket.getnameinfo
        original_sendto = socket.socket.sendto

        def guarded_create_connection(
            address: Any,
            *args: Any,
            **kwargs: Any,
        ) -> socket.socket:
            _ensure_loopback(address)
            return original_create_connection(address, *args, **kwargs)

        def guarded_connect(instance: socket.socket, address: Any) -> None:
            _ensure_loopback(address)
            return original_connect(instance, address)

        def guarded_connect_ex(instance: socket.socket, address: Any) -> int:
            _ensure_loopback(address)
            return original_connect_ex(instance, address)

        def guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> list[Any]:
            if host is not None:
                _ensure_loopback((host, 0))
            return original_getaddrinfo(host, *args, **kwargs)

        def guarded_gethostbyaddr(ip_address_value: str) -> tuple[str, list[str], list[str]]:
            _ensure_loopback((ip_address_value, 0))
            return original_gethostbyaddr(ip_address_value)

        def guarded_gethostbyname(host: str) -> str:
            _ensure_loopback((host, 0))
            return original_gethostbyname(host)

        def guarded_gethostbyname_ex(host: str) -> tuple[str, list[str], list[str]]:
            _ensure_loopback((host, 0))
            return original_gethostbyname_ex(host)

        def guarded_getnameinfo(sockaddr: tuple[Any, ...], flags: int) -> tuple[str, str]:
            _ensure_loopback(sockaddr)
            return original_getnameinfo(sockaddr, flags)

        def guarded_sendto(instance: socket.socket, data: Any, *args: Any) -> int:
            if args:
                _ensure_loopback(args[-1])
            return original_sendto(instance, data, *args)

        self._patch(socket, "create_connection", guarded_create_connection)
        self._patch(socket, "getaddrinfo", guarded_getaddrinfo)
        self._patch(socket, "gethostbyaddr", guarded_gethostbyaddr)
        self._patch(socket, "gethostbyname", guarded_gethostbyname)
        self._patch(socket, "gethostbyname_ex", guarded_gethostbyname_ex)
        self._patch(socket, "getnameinfo", guarded_getnameinfo)
        self._patch(socket.socket, "connect", guarded_connect)
        self._patch(socket.socket, "connect_ex", guarded_connect_ex)
        self._patch(socket.socket, "sendto", guarded_sendto)

    def restore(self) -> None:
        for owner, name, original in reversed(self._patches):
            setattr(owner, name, original)
        self._patches.clear()


def _command_text(command: object) -> str:
    if isinstance(command, bytes):
        return command.decode(errors="replace")
    if isinstance(command, str | os.PathLike):
        return os.fspath(command)
    if isinstance(command, Sequence):
        values = cast(Sequence[object], command)
        return " ".join(_command_text(value) for value in values)
    return str(command)


def _url_is_external(raw_url: str) -> bool:
    host = urlsplit(raw_url).hostname
    if host is None:
        return True
    try:
        return not ip_address(host.partition("%")[0]).is_loopback
    except ValueError:
        return host.casefold() != "localhost"


def reject_external_subprocess(command: object) -> None:
    text = _command_text(command)
    urls = _URL_PATTERN.findall(text)
    if any(_url_is_external(url) for url in urls):
        raise RuntimeError("subprocess network access is disabled during tests")
    if _NETWORK_CLIENT_PATTERN.search(text) or _WEB_COMMAND_PATTERN.search(text):
        raise RuntimeError("subprocess network access is disabled during tests")

    tokens = text.casefold().split()
    executable = Path(tokens[0]).stem if tokens else ""
    if executable == "git" and _GIT_NETWORK_COMMANDS.intersection(tokens[1:]):
        raise RuntimeError("subprocess network access is disabled during tests")


class SubprocessGuard:
    """Reject common native network clients before creating a child process."""

    def __init__(self) -> None:
        self._original_popen: Any = None

    def install(self) -> None:
        if self._original_popen is not None:
            return
        self._original_popen = subprocess.Popen
        subprocess.Popen = cast(Any, _GuardedPopen)

    def restore(self) -> None:
        if self._original_popen is not None:
            subprocess.Popen = self._original_popen
            self._original_popen = None


class _GuardedPopen(subprocess.Popen[Any]):
    def __init__(self, command: Any, *args: Any, **kwargs: Any) -> None:
        reject_external_subprocess(command)
        super().__init__(command, *args, **kwargs)


class PytestEnvironment:
    """Own process-wide pytest isolation and restore the caller exactly."""

    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root
        self._original_cwd = Path.cwd()
        self._original_environment = dict(os.environ)
        self._temporary_directory: tempfile.TemporaryDirectory[str] | None = None
        self._network_guard = NetworkGuard()
        self._subprocess_guard = SubprocessGuard()
        self.allow_live_provider = explicit_opt_in(
            self._original_environment,
            ALLOW_LIVE_PROVIDER_ENV,
        )
        self.allow_network = explicit_opt_in(
            self._original_environment,
            ALLOW_NETWORK_ENV,
        )

    def start(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory(prefix="pi-python-tests-")
        temporary_root = Path(self._temporary_directory.name)
        home = temporary_root / "home"
        workspace = temporary_root / "workspace"
        config = home / ".config"
        cache = home / ".cache"
        data = home / ".local" / "share"
        roaming = home / "AppData" / "Roaming"
        local = home / "AppData" / "Local"
        git_config = home / ".gitconfig"
        for directory in (home, workspace, config, cache, data, roaming, local):
            directory.mkdir(parents=True, exist_ok=True)
        git_config.touch()

        bootstrap_directory = self._repository_root / "tests" / "subprocess_bootstrap"
        pythonpath_parts = [str(bootstrap_directory), str(self._repository_root)]
        existing_pythonpath = os.environ.get("PYTHONPATH")
        if existing_pythonpath:
            pythonpath_parts.append(existing_pythonpath)

        os.environ.update(
            {
                "APPDATA": str(roaming),
                "GIT_CONFIG_GLOBAL": str(git_config),
                "GIT_CONFIG_NOSYSTEM": "1",
                "HOME": str(home),
                ISOLATION_MARKER_ENV: "1",
                "LOCALAPPDATA": str(local),
                "PI_PYTHON_COLLECTION_HOME": str(home),
                "PI_PYTHON_COLLECTION_WORKSPACE": str(workspace),
                "PYTHONPATH": os.pathsep.join(pythonpath_parts),
                SUBPROCESS_GUARD_ENV: "1",
                "USERPROFILE": str(home),
                "XDG_CACHE_HOME": str(cache),
                "XDG_CONFIG_HOME": str(config),
                "XDG_DATA_HOME": str(data),
            }
        )
        if not self.allow_live_provider:
            clear_sensitive_environment(os.environ)
        if not (self.allow_live_provider or self.allow_network):
            os.environ.update(
                {
                    "ALL_PROXY": "http://127.0.0.1:9",
                    "GIT_TERMINAL_PROMPT": "0",
                    "HTTPS_PROXY": "http://127.0.0.1:9",
                    "HTTP_PROXY": "http://127.0.0.1:9",
                    "NO_PROXY": "localhost,127.0.0.1,::1",
                    "NPM_CONFIG_OFFLINE": "true",
                    "PIP_NO_INDEX": "1",
                    "UV_OFFLINE": "1",
                }
            )
            self._network_guard.install()
            self._subprocess_guard.install()
        os.chdir(workspace)

    def restore(self) -> None:
        self._subprocess_guard.restore()
        self._network_guard.restore()
        os.chdir(self._original_cwd)
        os.environ.clear()
        os.environ.update(self._original_environment)
        if self._temporary_directory is not None:
            self._temporary_directory.cleanup()
            self._temporary_directory = None
