# ADR 0008: Python-only trailing torn-line session repair command

Status: Accepted (2026-08-30)

## Context

pi-python deliberately reads v3 Session files more strictly than upstream Pi
(SESSION-014, ADR 0003): a torn final record — the typical result of a crash
mid-append — makes the whole session fail to open. Upstream silently skips
damaged lines, which preserves availability but can silently drop history and
encourages working with partially read data. The validation report
(§20.3, RISK 1) identified the missing "repair" escape hatch as a real product
gap: a strict reader needs an explicit, auditable recovery path.

## Decision

- Add `pi-python session repair <path>`. It refuses to touch a file unless
  **exactly one condition** holds: the last non-empty record is torn at the
  JSON level (unterminated/unparsable) and dropping it leaves a structurally
  valid v3 session. In that case the file is atomically truncated to the
  valid prefix.
- Everything else is refused with exit 1 and the source bytes unchanged:
  - the file opens cleanly (nothing to repair);
  - damage on any record before the last line;
  - a last record that parses as JSON but is structurally invalid;
  - a torn header record;
  - a kept prefix that would still fail strict validation.
- Repair reuses the production strict reader (`read_session`) to validate the
  kept prefix through the same code path a later open will use.
- This command is a Python-only surface: upstream has no `session repair`.
  It is the counterpart to the stricter reader, not a change to it; a refused
  repair never mutates anything.

## Consequences

- Crash recovery no longer requires manual byte editing.
- The strictness guarantee "legal v3 bytes are never changed by a failed read
  or repair" remains intact: repair either refuses or removes only a record
  that was never a legal part of the session.
