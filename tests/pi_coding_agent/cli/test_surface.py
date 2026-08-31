"""Complete stable CLI surface snapshot (P12-T01)."""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

import pytest

from pi_coding_agent.cli.main import main
from pi_coding_agent.cli.parser import create_parser, create_run_parser, parse_run_arguments
from pi_coding_agent.cli.surface import UnknownFlagError, split_unknown_flags


def _parse(argv: list[str]):
    parser = create_run_parser(version=version("pi-python"))
    return parser.parse_args([*argv])


class TestStaticFlags:
    def test_prompt_and_system_prompt_flags(self) -> None:
        args = _parse(["--system-prompt", "base", "--append-system-prompt", "one", "-p"])
        assert args.system_prompt == "base"
        assert args.append_system_prompt == ["one"]

    def test_append_system_prompt_is_repeatable(self) -> None:
        args = _parse(["--append-system-prompt", "one", "--append-system-prompt", "two"])
        assert args.append_system_prompt == ["one", "two"]

    def test_session_selection_flags(self) -> None:
        args = _parse(["--session-id", "0123456789abcdef0123456789abcdef"])
        assert args.session_id == "0123456789abcdef0123456789abcdef"
        args = _parse(["--fork", "source.jsonl"])
        assert args.fork == "source.jsonl"

    def test_models_flag_is_comma_scoped(self) -> None:
        args = _parse(["--models", "flash, pro"])
        assert args.models == ["flash", "pro"]

    def test_resource_flags(self) -> None:
        args = _parse(
            [
                "--extension",
                "ext1.py",
                "-e",
                "ext2.py",
                "--no-extensions",
                "--skill",
                "s1",
                "--no-skills",
                "--prompt-template",
                "p1",
                "--no-prompt-templates",
                "--theme",
                "t1",
                "--use-theme",
                "dark",
                "--no-themes",
                "--no-context-files",
            ]
        )
        assert args.extension == ["ext1.py", "ext2.py"]
        assert args.no_extensions is True
        assert args.skill == ["s1"]
        assert args.no_skills is True
        assert args.prompt_template == ["p1"]
        assert args.no_prompt_templates is True
        assert args.theme == ["t1"]
        assert args.use_theme == "dark"
        assert args.no_themes is True
        assert args.no_context_files is True

    def test_trust_and_mode_flags(self) -> None:
        assert _parse(["--approve"]).approve is True
        assert _parse(["-a"]).approve is True
        assert _parse(["--no-approve", "-na"]).no_approve is True
        assert _parse(["--offline"]).offline is True
        assert _parse(["--verbose"]).verbose is True
        assert _parse(["--mode", "rpc"]).mode == "rpc"

    def test_export_flag_parses(self) -> None:
        args = _parse(["--export", "session-file", "out.html"])
        assert args.export == "session-file"
        assert args.messages == ["out.html"]


class TestTwoPhaseParsing:
    def test_unknown_long_flags_become_extension_flags(self) -> None:
        _arguments, unknown = create_run_parser(version="t").parse_known_args(
            ["--extflag", "--other=value", "hello"]
        )
        mapping = split_unknown_flags(unknown)
        assert mapping == {"extflag": True, "other": "value"}

    def test_unknown_short_flags_are_rejected(self) -> None:
        parser = create_run_parser(version="t")
        with pytest.raises(SystemExit):
            parser.parse_args(["-q", "hello"])

    def test_split_unknown_flags_rejects_short_options(self) -> None:
        with pytest.raises(UnknownFlagError):
            split_unknown_flags(["-q"])

    def test_unknown_string_flag_consumes_its_value_before_static_parsing(self) -> None:
        parser = create_run_parser(version="t")

        arguments, unknown = parse_run_arguments(
            parser,
            ["--extension-setting", "value", "continue the task"],
        )

        assert unknown == {"extension-setting": "value"}
        assert arguments.messages == ["continue the task"]

    def test_unknown_boolean_flag_does_not_consume_a_file_argument(self) -> None:
        parser = create_run_parser(version="t")

        arguments, unknown = parse_run_arguments(parser, ["--plan", "@context.md"])

        assert unknown == {"plan": True}
        assert arguments.messages == ["@context.md"]


class TestPackageSubcommands:
    def test_install_and_remove_parse(self) -> None:
        parser = create_parser(version="t")
        args = parser.parse_args(["install", "some-source", "--local"])
        assert args.command == "install"
        assert args.source == "some-source"
        assert args.local is True

    def test_update_flags_parse(self) -> None:
        parser = create_parser(version="t")
        args = parser.parse_args(["update", "--all", "--force"])
        assert args.command == "update"
        assert args.all is True
        assert args.force is True

    def test_list_and_config_parse(self) -> None:
        parser = create_parser(version="t")
        args = parser.parse_args(["list"])
        assert args.command == "list"
        args = parser.parse_args(["config", "--local", "name", "enabled"])
        assert args.command == "config"
        assert args.local is True

    def test_config_parses_without_a_resource_name_for_the_interactive_surface(self) -> None:
        parser = create_parser(version="t")

        args = parser.parse_args(["config", "--local"])

        assert args.command == "config"
        assert args.local is True
        assert args.name is None

    def test_uninstall_alias(self) -> None:
        parser = create_parser(version="t")
        args = parser.parse_args(["uninstall", "x"])
        assert args.command == "uninstall"

    def test_package_without_command_fails(self) -> None:
        parser = create_parser(version="t")
        with pytest.raises(SystemExit):
            parser.parse_args(["install"])


class TestCommandRouting:
    def test_package_commands_reach_the_package_adapter(self, tmp_path: Path) -> None:
        from io import StringIO

        errors = StringIO()
        code = main(
            ["list"],
            stdout=StringIO(),
            stderr=errors,
            cwd=tmp_path,
            environ={},
        )

        assert code == 0
        assert errors.getvalue() == ""

    def test_mode_rpc_reports_clean_error(self, tmp_path: Path) -> None:
        from io import StringIO

        errors = StringIO()
        code = main(
            ["--mode", "rpc", "-p", "hi"],
            stdout=StringIO(),
            stderr=errors,
            cwd=tmp_path,
            environ={},
        )
        assert code == 1
        assert "rpc" in errors.getvalue().lower()

    def test_auth_rejects_credentials_flag(self, tmp_path: Path) -> None:
        parser = create_parser(version="t")
        with pytest.raises(SystemExit):
            parser.parse_args(["auth", "check", "--credentials"])
