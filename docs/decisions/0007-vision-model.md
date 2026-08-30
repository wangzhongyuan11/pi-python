# ADR 0007: DeepSeek vision model catalog entry

Status: Accepted (2026-08-30)

## Context

The frozen upstream baseline ships multi-provider catalogs; pi-python is DeepSeek-only by
design (ADR 0005). The product goal for 1.0 includes image input parity: `read` on image
files, image attachments, and a model that accepts them. That requires a catalog entry with
`input=("text", "image")` for an actually available DeepSeek model.

`deepseek-v4-flash-vision-exp` was verified against the live API on 2026-08-30:

- A text-only chat completion returned HTTP 200.
- A chat completion with an `image_url` data URL carrying a valid PNG returned HTTP 200;
  an invalid image body returned the documented 400 `invalid_request_error` for unsupported
  image formats (webp/png/jpeg/gif accepted).
- The response included non-empty `reasoning_content` and a correct final answer for a
  "what color dominates this image" question over a synthetic blue PNG, plus usage with
  `reasoning_tokens`, confirming vision input and DeepSeek-style thinking output.

## Decision

- Add `deepseek-v4-flash-vision-exp` to the controlled catalog with
  `input=("text", "image")`, `reasoning=True`, and the same compat/thinking mapping as the
  other DeepSeek models.
- `context_window=1_000_000`, `max_tokens=384_000`, and the Flash cost rates are mirrored
  from `deepseek-v4-flash` pending an official spec sheet for the experimental model. These
  values gate threshold compaction and cost reporting; they are reviewed assumptions, not
  measured facts, and must be revisited when DeepSeek publishes the model officially.
- The experimental model is never the default: `DEFAULT_DEEPSEEK_MODEL` stays
  `deepseek-v4-pro`. It must be selected explicitly via `--model`, `/model`, or settings.
- Text-only models keep rejecting image content at request-build time
  (`DeepSeekCapabilityError`), so the capability error path stays exercised for flash/pro.

## Consequences

- Tool and attachment code can branch on `model.input` instead of hard-coded model ids.
- If DeepSeek retires the experimental model, the live smoke in the release checklist fails;
  the catalog entry is then removed or replaced via a new ADR, never silently.
