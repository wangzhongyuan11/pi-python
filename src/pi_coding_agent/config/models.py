"""Validated settings models at the JSON boundary."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class SettingsValidationError(ValueError):
    pass


class _SettingsModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        frozen=True,
    )


type NonNegativeInt = Annotated[int, Field(ge=0)]


class CompactionSettings(_SettingsModel):
    enabled: bool = True
    reserve_tokens: NonNegativeInt = 16_384
    keep_recent_tokens: NonNegativeInt = 20_000


class BranchSummarySettings(_SettingsModel):
    reserve_tokens: NonNegativeInt = 16_384
    skip_prompt: bool = False


class ProviderRetrySettings(_SettingsModel):
    timeout_ms: NonNegativeInt = 300_000
    max_retries: NonNegativeInt = 0
    max_retry_delay_ms: NonNegativeInt = 60_000


class RetrySettings(_SettingsModel):
    enabled: bool = True
    max_retries: NonNegativeInt = 3
    base_delay_ms: NonNegativeInt = 2_000
    provider: ProviderRetrySettings = ProviderRetrySettings()


class TerminalSettings(_SettingsModel):
    show_images: bool = True
    image_width_cells: Annotated[int, Field(gt=0)] = 60
    clear_on_shrink: bool = False
    show_terminal_progress: bool = False


class ImageSettings(_SettingsModel):
    auto_resize: bool = True
    block_images: bool = False


class ThinkingBudgetsSettings(_SettingsModel):
    minimal: NonNegativeInt | None = None
    low: NonNegativeInt | None = None
    medium: NonNegativeInt | None = None
    high: NonNegativeInt | None = None


class MarkdownSettings(_SettingsModel):
    code_block_indent: str = "  "
    mermaid: Literal["off", "final", "streaming"] = "streaming"


class PackageSource(_SettingsModel):
    source: str
    autoload: bool = True
    extensions: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    prompts: tuple[str, ...] = ()
    themes: tuple[str, ...] = ()


class SettingsValues(_SettingsModel):
    last_changelog_version: str | None = None
    default_provider: str | None = None
    default_model: str | None = None
    default_thinking_level: Literal["off", "minimal", "low", "medium", "high"] | None = None
    transport: Literal["auto", "sse"] = "auto"
    steering_mode: Literal["all", "one-at-a-time"] = "one-at-a-time"
    follow_up_mode: Literal["all", "one-at-a-time"] = "one-at-a-time"
    theme: str | None = None
    compaction: CompactionSettings = CompactionSettings()
    branch_summary: BranchSummarySettings = BranchSummarySettings()
    retry: RetrySettings = RetrySettings()
    hide_thinking_block: bool = False
    show_cache_miss_notices: bool = False
    external_editor: str | None = None
    shell_path: str | None = None
    quiet_startup: bool = False
    default_project_trust: Literal["ask", "always", "never"] = "ask"
    shell_command_prefix: str | None = None
    npm_command: tuple[str, ...] = ()
    collapse_changelog: bool = False
    packages: tuple[str | PackageSource, ...] = ()
    extensions: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    prompts: tuple[str, ...] = ()
    themes: tuple[str, ...] = ()
    enable_skill_commands: bool = True
    terminal: TerminalSettings = TerminalSettings()
    images: ImageSettings = ImageSettings()
    enabled_models: tuple[str, ...] = ()
    default_tools: tuple[str, ...] = ()
    double_escape_action: Literal["fork", "tree", "none"] = "tree"
    tree_filter_mode: Literal["default", "no-tools", "user-only", "labeled-only", "all"] = "default"
    thinking_budgets: ThinkingBudgetsSettings = ThinkingBudgetsSettings()
    editor_padding_x: NonNegativeInt = 0
    output_pad: Literal[0, 1] = 1
    autocomplete_max_visible: Annotated[int, Field(gt=0)] = 5
    show_hardware_cursor: bool = False
    markdown: MarkdownSettings = MarkdownSettings()
    session_dir: str | None = None
    http_proxy: str | None = None
    http_idle_timeout_ms: NonNegativeInt = 300_000
    websocket_connect_timeout_ms: None = None
    tui_mode: Literal["regular", "fullscreen"] = "regular"
    fullscreen_exit_output: Literal["transcript", "resume-hint"] = "transcript"
    fullscreen_scrollbar: Literal["hidden", "auto", "always"] = "auto"

    @field_validator("websocket_connect_timeout_ms", mode="before")
    @classmethod
    def _reject_websocket_setting(cls, value: object) -> None:
        if value is not None:
            raise ValueError("websocket transport is not supported; use SSE settings")
        return None


KNOWN_SETTING_ALIASES = frozenset(
    field.alias or name for name, field in SettingsValues.model_fields.items()
)


def settings_payload(values: SettingsValues) -> dict[str, Any]:
    return values.model_dump(by_alias=True, mode="json")


__all__ = [
    "BranchSummarySettings",
    "CompactionSettings",
    "ImageSettings",
    "KNOWN_SETTING_ALIASES",
    "PackageSource",
    "MarkdownSettings",
    "ProviderRetrySettings",
    "RetrySettings",
    "SettingsValidationError",
    "SettingsValues",
    "TerminalSettings",
    "ThinkingBudgetsSettings",
    "settings_payload",
]
