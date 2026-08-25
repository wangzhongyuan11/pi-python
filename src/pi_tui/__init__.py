"""Terminal UI boundary for the Pi Python distribution."""

from importlib.metadata import version as _distribution_version

from .actions import TUI_ACTIONS, ActionDefinition
from .application import Application
from .autocomplete import Autocompleter, CompletionProvider
from .components import Box, Component, HStack, Status, Text, VStack, render_lines
from .dialogs import Dialog, SelectList
from .editor import Editor
from .history import InputHistory
from .keybindings import KeybindingRegistry
from .layout import wrap_text
from .overlays import OverlayStack
from .paste import BracketedPasteParser
from .protocols import UI, MemoryUI, NoopUI, NotificationLevel
from .render import ScreenRenderer
from .terminal import PromptToolkitTerminal, TuiInput, TuiOutput
from .testing import MemoryTerminal
from .theme import Theme, ThemeColor, create_theme
from .width import (
    pad_to_width,
    sanitize_terminal_text,
    strip_ansi,
    truncate_to_width,
    visible_width,
)

__version__ = _distribution_version("pi-python")

__all__ = [
    "ActionDefinition",
    "Application",
    "Autocompleter",
    "Box",
    "BracketedPasteParser",
    "CompletionProvider",
    "Component",
    "Dialog",
    "Editor",
    "HStack",
    "InputHistory",
    "KeybindingRegistry",
    "MemoryUI",
    "MemoryTerminal",
    "NoopUI",
    "NotificationLevel",
    "OverlayStack",
    "PromptToolkitTerminal",
    "ScreenRenderer",
    "SelectList",
    "Status",
    "TUI_ACTIONS",
    "Text",
    "Theme",
    "ThemeColor",
    "TuiInput",
    "TuiOutput",
    "UI",
    "VStack",
    "__version__",
    "create_theme",
    "pad_to_width",
    "render_lines",
    "sanitize_terminal_text",
    "strip_ansi",
    "truncate_to_width",
    "visible_width",
    "wrap_text",
]
