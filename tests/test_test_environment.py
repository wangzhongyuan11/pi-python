from __future__ import annotations

import os
import socket
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _collection_network_error() -> str | None:
    try:
        socket.getaddrinfo("203.0.113.1", 443)
    except RuntimeError as exc:
        return str(exc)
    return None


COLLECTION_HOME = Path.home()
COLLECTION_CWD = Path.cwd()
COLLECTION_ISOLATED = os.environ.get("PI_PYTHON_TEST_ISOLATED") == "1"
COLLECTION_NETWORK_ERROR = _collection_network_error()


def test_home_and_user_config_are_isolated(isolated_home: Path) -> None:
    assert Path.home() == isolated_home
    assert Path(os.environ["XDG_CONFIG_HOME"]).is_relative_to(isolated_home)
    assert Path(os.environ["XDG_CACHE_HOME"]).is_relative_to(isolated_home)
    assert Path(os.environ["XDG_DATA_HOME"]).is_relative_to(isolated_home)
    assert Path(os.environ["APPDATA"]).is_relative_to(isolated_home)
    assert Path(os.environ["LOCALAPPDATA"]).is_relative_to(isolated_home)


def test_home_is_isolated_before_test_collection() -> None:
    assert COLLECTION_ISOLATED
    assert COLLECTION_HOME == Path(os.environ["PI_PYTHON_COLLECTION_HOME"])


def test_cwd_is_an_empty_workspace_before_test_collection() -> None:
    assert COLLECTION_CWD == Path(os.environ["PI_PYTHON_COLLECTION_WORKSPACE"])
    assert COLLECTION_CWD != REPOSITORY_ROOT
    assert not (COLLECTION_CWD / ".env").exists()
    assert list(COLLECTION_CWD.iterdir()) == []


def test_git_global_configuration_is_isolated(isolated_home: Path) -> None:
    git_config = Path(os.environ["GIT_CONFIG_GLOBAL"])

    assert git_config == isolated_home / ".gitconfig"
    assert git_config.read_text(encoding="utf-8") == ""
    assert os.environ["GIT_CONFIG_NOSYSTEM"] == "1"


def test_provider_api_keys_are_cleared(cleared_api_keys: None) -> None:
    del cleared_api_keys

    assert not [name for name in os.environ if name.upper().endswith("_API_KEY")]


@pytest.mark.parametrize(
    "name",
    [
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "AWS_ACCESS_KEY_ID",
        "AWS_PROFILE",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AZURE_CLIENT_ID",
        "AZURE_CLIENT_SECRET",
        "AZURE_TENANT_ID",
        "GITHUB_PAT",
    ],
)
def test_common_provider_and_cloud_credentials_are_cleared(name: str) -> None:
    assert name not in os.environ


def test_external_network_is_blocked_by_default(no_external_network: None) -> None:
    del no_external_network

    with pytest.raises(RuntimeError, match="external network is disabled"):
        socket.create_connection(("example.invalid", 443))


def test_external_network_is_blocked_before_test_collection() -> None:
    assert COLLECTION_NETWORK_ERROR is not None
    assert "external network is disabled" in COLLECTION_NETWORK_ERROR


def test_tcp_udp_and_dns_entry_points_are_blocked() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
        with pytest.raises(RuntimeError, match="external network is disabled"):
            tcp_socket.connect(("203.0.113.1", 443))
        with pytest.raises(RuntimeError, match="external network is disabled"):
            tcp_socket.connect_ex(("203.0.113.1", 443))

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        with pytest.raises(RuntimeError, match="external network is disabled"):
            udp_socket.sendto(b"probe", ("203.0.113.1", 53))

    with pytest.raises(RuntimeError, match="external network is disabled"):
        socket.getaddrinfo("203.0.113.1", 443)
    with pytest.raises(RuntimeError, match="external network is disabled"):
        socket.gethostbyname("example.invalid")


def test_python_subprocess_inherits_the_network_guard() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import socket; socket.getaddrinfo('203.0.113.1', 443)",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "external network is disabled" in result.stderr


def test_known_native_network_clients_are_rejected_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))

    with pytest.raises(RuntimeError, match="subprocess network access is disabled"):
        subprocess.run(
            ["curl", "https://example.invalid"],
            check=False,
            capture_output=True,
            text=True,
        )


def test_pytest_bootstrap_restores_the_callers_environment(tmp_path: Path) -> None:
    probe = tmp_path / "collection_probe.py"
    probe.write_text(
        textwrap.dedent(
            """
            import os
            import socket
            from pathlib import Path

            assert "DEEPSEEK_API_KEY" not in os.environ
            assert Path.home() != Path(os.environ["PI_PYTHON_CALLER_HOME"])
            assert Path.cwd() == Path(os.environ["PI_PYTHON_COLLECTION_WORKSPACE"])
            assert not (Path.cwd() / ".env").exists()
            try:
                socket.getaddrinfo("203.0.113.1", 443)
            except RuntimeError as exc:
                assert "external network is disabled" in str(exc)
            else:
                raise AssertionError("network guard was not active during collection")

            def test_probe() -> None:
                pass
            """
        ),
        encoding="utf-8",
    )
    caller_home = tmp_path / "caller-home"
    runner = textwrap.dedent(
        f"""
        import os
        from pathlib import Path
        import pytest

        caller_home = Path({str(caller_home)!r})
        os.environ["HOME"] = str(caller_home)
        os.environ["USERPROFILE"] = str(caller_home)
        os.environ["PI_PYTHON_CALLER_HOME"] = str(caller_home)
        os.environ["PI_PYTHON_CALLER_CWD"] = os.getcwd()
        os.environ["DEEPSEEK_API_KEY"] = "caller-sentinel"
        result = pytest.main([
            "-p", "tests.conftest",
            "--rootdir", {str(REPOSITORY_ROOT)!r},
            {str(probe)!r},
            "-q",
        ])
        assert result == pytest.ExitCode.OK, result
        assert os.environ["HOME"] == str(caller_home)
        assert os.environ["USERPROFILE"] == str(caller_home)
        assert os.environ["DEEPSEEK_API_KEY"] == "caller-sentinel"
        assert os.getcwd() == os.environ["PI_PYTHON_CALLER_CWD"]
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", runner],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPOSITORY_ROOT,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_workspace_is_an_empty_temporary_directory(workspace: Path) -> None:
    assert workspace.is_dir()
    assert list(workspace.iterdir()) == []
