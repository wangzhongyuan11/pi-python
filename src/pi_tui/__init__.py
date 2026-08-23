"""Terminal UI boundary for the Pi Python distribution."""

from importlib.metadata import version as _distribution_version

from .protocols import UI, MemoryUI, NoopUI, NotificationLevel
from .theme import Theme, ThemeColor, create_theme

__version__ = _distribution_version("pi-python")

__all__ = [
    "MemoryUI",
    "NoopUI",
    "NotificationLevel",
    "Theme",
    "ThemeColor",
    "UI",
    "__version__",
    "create_theme",
]
