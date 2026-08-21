# Agent contribution rules

These rules apply to every implementation task in this repository.

## Source of truth

1. `tasks/todo.md` is the only execution backlog.
2. `tasks/plan.md` defines architecture, scope, and phase acceptance.
3. `docs/contracts/` and `docs/compatibility/surface-matrix.md` define frozen behavior.
4. `D:\pi` at commit `e14afc648e10fb6c527ea88fa627091ada764306` is the upstream oracle.

Do not infer behavior from the tutorial when current source or tests answer the question.

## Work unit

- Work on exactly one todo ID at a time.
- One todo ID changes one observable behavior and produces one atomic commit.
- Use branch `phase/NN-name` and commit `P<n>-T<nn>: ...`.
- Touch only the files required by the task. Do not refactor adjacent code.
- Stop after every phase and wait for user acceptance before merging or starting the next phase.

## Test-first loop

1. Add the smallest failing behavioral test.
2. Run it and retain the failure reason.
3. Implement the minimum behavior needed to pass.
4. Run the focused command in `tasks/todo.md`.
5. Run the phase regression gate.
6. Review the diff and commit only the task's files.

Do not weaken, delete, skip, or over-mock a test to make it pass.

## Package boundaries

- `pi_telemetry` imports no other project package.
- `pi_ai` may import only `pi_telemetry`.
- `pi_agent` may import only `pi_ai` and `pi_telemetry`.
- `pi_tui` must not import any other `pi_*` package; product telemetry belongs in
  `pi_coding_agent`.
- `pi_coding_agent` is the only product composition package.

## Safety

- Treat model output, project resources, Session data, package metadata, paths, and tool arguments as untrusted.
- Never commit `.env`, credentials, Authorization headers, tokens, private keys, or captured secret values.
- Never print secret values in tests, logs, exceptions, diffs, or review output.
- Never run live Provider tests without explicit approval for that exact run.
- Default tests must remain isolated from real HOME/cwd/configuration and use fake
  operations for native subprocesses; network/live markers also require their
  explicit environment opt-in and approval for that exact run.
- Do not run `npm run check`, formatters, code generation, or any other mutation-capable command in `D:\pi`.
- Read upstream directly or work on a disposable copy when an experiment is necessary.

## Compatibility discipline

- Every public surface is classified as `Supported`, `Intentional divergence`, or `Post-v1`.
- Do not silently change a classification. Update the surface matrix and add an ADR first.
- Preserve v3 Session bytes on read failures and never replay an unmatched recovered Tool Call.
- Provider request retries and AgentSession turn retries must remain separately observable.
