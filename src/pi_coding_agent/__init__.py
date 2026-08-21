"""Composition-root boundary for the Pi Python distribution."""

from importlib.metadata import version as _distribution_version

__version__ = _distribution_version("pi-python")

__all__ = ["__version__"]
