"""Propagate the pytest isolation policy into Python child processes."""

from __future__ import annotations

import os

if os.environ.get("PI_PYTHON_TEST_SUBPROCESS_GUARD") == "1":
    from tests._bootstrap import (
        ALLOW_LIVE_PROVIDER_ENV,
        ALLOW_NETWORK_ENV,
        NetworkGuard,
        SubprocessGuard,
        clear_sensitive_environment,
        explicit_opt_in,
    )

    allow_live_provider = explicit_opt_in(os.environ, ALLOW_LIVE_PROVIDER_ENV)
    allow_network = explicit_opt_in(os.environ, ALLOW_NETWORK_ENV)
    if not allow_live_provider:
        clear_sensitive_environment(os.environ)
    if not (allow_live_provider or allow_network):
        _PI_TEST_NETWORK_GUARD = NetworkGuard()
        _PI_TEST_NETWORK_GUARD.install()
        _PI_TEST_SUBPROCESS_GUARD = SubprocessGuard()
        _PI_TEST_SUBPROCESS_GUARD.install()
