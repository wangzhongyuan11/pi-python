# ADR 0009: Dual-runtime Pi package and extension compatibility

Status: Accepted (2026-09-03)

## Context

pi-python currently installs local, Git, PyPI, and data-only npm packages, but
executes extensions only through the Python `pi-extension.json` + `main.py`
contract. Upstream Pi packages use `package.json#pi`, conventional resource
directories, npm dependencies, and JavaScript or TypeScript extensions loaded
with Jiti. Rejecting every JavaScript or TypeScript file prevents reuse of the
existing Pi package ecosystem.

The Python Agent, Session, Provider, tool registry, and TUI remain the product
owners. Running the complete upstream coding agent as a child process would
duplicate those owners and make the Python product a wrapper rather than a
rewrite.

## Decision

- Keep the existing Python extension runtime as a native, supported surface.
- Accept upstream package source syntax and `package.json#pi` resource
  declarations, including conventional directories and include/exclude
  filters.
- Classify package contents before activation as:
  - `native`: Python extensions executed by the Python runtime;
  - `portable`: skills, prompts, and themes loaded directly by Python;
  - `bridged`: JavaScript or TypeScript extensions requiring the Node host;
  - `unsupported`: capabilities that cannot be represented by the negotiated
    bridge version.
- Add a versioned Node extension host after the local RPC foundations. The host
  loads upstream extensions in Node and exposes only negotiated Extension API
  capabilities to the Python product. Python continues to own AgentSession,
  tools, model calls, persistence, cwd, and TUI state.
- Do not translate TypeScript to Python and do not silently ignore unsupported
  capabilities. Installation and inspection report them explicitly.
- Installing an npm package may fetch and unpack JavaScript or TypeScript but
  must not execute extension code or lifecycle scripts until the Node host is
  explicitly activated. Runtime dependencies are installed by the later Node
  host phase.

## Consequences

- Existing Python packages and extensions remain compatible.
- Portable resources from upstream packages can work before the Node host is
  implemented; bridged extensions are preserved and diagnosed meanwhile.
- Common tools, commands, flags, shortcuts, hooks, session actions, and simple
  UI requests can be compatible without changing upstream extension source.
- JavaScript TUI component objects and private upstream internals cannot cross
  the process boundary directly. They remain unsupported until an equivalent
  serializable Python TUI contract exists.
- Phase 15 owns reusable framing, request correlation, cancellation,
  backpressure, and subprocess cleanup. Phase 15.5 builds the Node host on that
  substrate, and Phase 16 validates both extension runtimes together.
