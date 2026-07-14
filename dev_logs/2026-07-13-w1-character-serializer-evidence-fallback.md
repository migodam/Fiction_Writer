# W1 Character Serializer Evidence Fallback - 2026-07-13

## Scope

- Modified: `sidecar/workflows/w1_import.py` and `tests/test_w1_import_compiler.py`.
- No supervisor, frontend, network, provider, or live-import changes.

## Change

- At the final character-create proposal boundary, structured `experience`/`experiences` still takes precedence.
- When those fields are empty, any character with a resolvable evidence reference and complete source span may recover up to three provenance-tagged `[window ...]` action/state notes as frontend `Character.experience` rows. Background recovery remains limited to core/major characters.
- Fallback rows have stable character-scoped IDs and carry the existing evidence-card ID. Trait-only and open-question notes are excluded.
- Empty backgrounds for those supported characters use only literal identity/origin/role clauses, with the evidence reference and source span recorded in `profile_field_evidence`.
- The action/state allowlist now recognizes the exact live-smoke state transitions `毫无进展` and `允诺`; these remain evidence-gated and do not admit free-form personality claims.

## Coverage

- Added latest live-smoke-shaped 韩立, 墨大夫, and 张铁 payload regressions, including their evidence refs and source spans.
- Asserted frontend-compatible experience rows, resolvable evidence provenance, an identity-only 墨大夫 background, and no fallback for a sparse supporting character.
- Added a cap regression for three stable character-scoped experience IDs.

## Deterministic Replay

- Replayed the exact 张铁 proposal from `/tmp/narrative_ide_w1_live_smoke/20260713_033431/project/system/inbox.json` without modifying the artifact or calling a provider.
- Before replay: `experience: []`.
- After replay: `在无名口诀上毫无进展` and `被墨大夫允诺另传心法`, both bound to `evc_67317f8af15e` and the original verified source span.
- This was the only hard semantic failure in that Flash run; all extraction, evidence, dedupe, timeline, tag, relationship, World, source-span, usage, and secret gates had already passed.

## Verification

- Focused character fallback regressions -> `2 passed`.
- Full W1 backend suite -> `658 passed in 9.69s`.
- `sidecar/.venv/bin/python -m compileall -q sidecar tools` -> passed.
- `git diff --check` -> passed.
