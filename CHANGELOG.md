# Changelog

All notable changes to this project will be documented here.

## Unreleased

### Phase 11.5 product completion

- Wire the pinned/system ripgrep and fd binaries into the production tool
  factory: `grep`, `find`, and `ls` are now reachable in real sessions, and
  `--tools all` selects all seven built-ins (default remains
  read/bash/edit/write; the read-only set read/grep/find/ls is exposed via
  `create_readonly_tools`).
- Add CLI tool selection flags `--tools/-t`, `--exclude-tools/-xt`,
  `--no-tools/-nt`, and `--no-builtin-tools/-nbt`, plus the `defaultTools`
  setting, all applied in the shared session composition.
- Add threshold auto-compaction driven by the `compaction.reserveTokens` and
  `compaction.keepRecentTokens` settings with a model-backed summarizer, a
  `/compact` slash command, and upstream-aligned skip semantics when nothing
  can be summarized.
- Add the `deepseek-v4-flash-vision-exp` catalog entry (ADR 0007), inline
  image reads in the `read` tool (png/jpeg/gif/webp; bmp omitted with a hint),
  and the vision request path including the actionable pre-request rejection
  for text-only models.
- Edit results now carry `diff`, `patch`, and `firstChangedLine` details
  (ported from upstream edit-diff) with tiered fuzzy matching (NFKC, smart
  quotes/dashes, trailing whitespace) and a TUI diff summary row.
- The bash tool now exposes `PI_*` session environment variables, applies the
  `shellCommandPrefix` setting, prepends the agent binary cache dir to `PATH`,
  and throttles streaming updates.
- Add `--name/-n` (session display names via `session_info`), the
  `pi-python session repair` command for trailing torn records (ADR 0008),
  and open-or-create semantics for missing valid session ids.
- Surface verbatim capability errors for text-only models given image input
  instead of a generic failure message.

### Phase 11 gap closure

- Surface compaction activity as product events: `compaction_start` and `compaction_end`
  now flow through the `AgentSessionEvent` stream, the JSON presenter, and the interactive
  status line.
- Skip extension slash commands that conflict with product commands at startup, reporting
  the skipped names on stderr instead of failing to launch.
- Add `/copy` to copy the last reply to the terminal clipboard over OSC-52, with a raw
  command outcome channel that bypasses the sanitized transcript.
- Add `/attach <path>` for file and image attachments on the next prompt; image support
  is derived from the selected model's input capabilities instead of a manual flag.
- Bind session navigation into the interactive loop: `/sessions` lists saved sessions and
  switches by number, `/fork` forks the current session into a new child file; both
  rebuild the renderer around the runtime's replacement session while preserving the
  transcript.
- Drive the Windows smoke through a real OS subprocess running the product loop, and make
  the platform-specific checks skip cleanly outside Windows.

## 0.5.0 - 2026-08-26

### Phase 11

- Add the interactive coding agent TUI on `pi_tui`: assistant message stream rendering,
  in-place tool lifecycle rows, retry and compaction status lines, session selector with
  real runtime switch/fork actions, persisted provider-qualified model and thinking
  selection, slash command dispatch backed by extension registrations, isolated extension
  dialogs, regular/fullscreen terminal modes, paste and attachment contracts, the frozen
  product action registry, and width-safe rendering verified by a Windows smoke test.

## 0.4.0 - 2026-08-25

### Phase 9–10

- Add the generic `pi_tui` package: prompt_toolkit terminal adapters, in-memory test
  terminal, foundational Text/Stack/Box/Status components, a reusable editor with
  unicode-safe cursor ops, undo, and input history, modal dialogs and overlay stacks,
  clean streaming/resize rendering, display-width handling for CJK and ANSI, a frozen
  action/keybinding registry with documentation, and bracketed paste plus word
  completion with an empty `pi_*` import allowlist.
- Add the extension and package foundation: trust-gated two-phase extension loading,
  isolated hook execution, conflict-detecting capability registry, UI/auth bridge
  ports with renderers and session actions, local/Git/PyPI package resolution with
  ref-drift detection, managed environments with atomic lockfiles and rollback,
  npm data ingestion without script execution, the default resource loader, and a
  reload-safe lifecycle.

## 0.3.0 - 2026-08-24

### Phase 7–8

- Add layered settings loading, canonical Python configuration paths with legacy
  environment compatibility, project trust gating, deterministic resource precedence,
  read-only `.pi` compatibility mounts, context/system prompt assembly, and lazy
  prompt/skill/theme resources.
- Add AgentSession product event layering, bounded whole-turn retries with observable
  attempt metadata, isolated context overflow recovery, safe compaction cutpoints,
  incremental compaction summaries, divergent branch diffs, branch file operation
  tracking, persisted branch summaries, and session state/tree view restoration.

## 0.2.0 - 2026-08-24

### Phase 4–6

- Add the reviewed DeepSeek V4 Flash/Pro streaming provider, safe credential precedence,
  explicit request retry controls, and the default Pro model runtime.
- Add the seven coding tools with atomic mutation, cancellation, deterministic ordering,
  Bash discovery, output truncation, and hash-verified search binary management.
- Add AgentSession ownership, cwd-aware lifecycle replacement, async and synchronous SDKs,
  v3 import, headless text/JSON CLI modes, and conservative unmatched Tool Call recovery.
- Add the `pi-python` console entry point with model listing, credential readiness checks,
  explicit key printing, Session selection, and stable exit/output contracts.

## 0.1.0 - 2026-08-24

### Phase 1–3

- Add telemetry, AI wire contracts, deterministic provider streams, and the core Agent loop.
- Add strict Session v3 models, append-only persistence, tree navigation, context projection,
  fork/open/list/export/import operations, and a read-only TypeScript interoperability oracle.
- Freeze product service ports and generic UI protocols with deterministic no-op implementations.
- Verify wheel installation and all five package imports from outside the repository.

### Phase 0

- Freeze the Pi `0.84.1` source baseline at commit `e14afc648e10fb6c527ea88fa627091ada764306`.
- Define the one-distribution, five-package Python architecture.
- Establish public contracts, compatibility classifications, and the security threat model.
- Add deterministic offline tests, a read-only TypeScript oracle, static checks, CI, dependency auditing, and secret scanning.

No Agent runtime or end-user CLI behavior is implemented in Phase 0.
