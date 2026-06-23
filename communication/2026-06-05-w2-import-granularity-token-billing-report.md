# Worker W2 — Import Granularity Controls + Token Billing/Cost Display
**Date:** 2026-06-05
**Branch:** codex/w1-orchestrated-import-quality

---

## Executive Summary

Two production UX issues resolved: the import workflow now exposes 8 named presets with extraction toggles instead of 4 opaque technical profile names, and the token cost card no longer shows "unavailable" for `deepseek-v4-flash`, `deepseek-v4-pro`, or `claude-sonnet-4-6`.

---

## Root Cause Analysis

### Problem 1: Import UI exposes too few granularity options

The previous UI offered `fast / balanced / deep / custom` with no plain-language description of scope. "Custom" mode hid all 9 technical knobs behind a dropdown, requiring users to know what `arc_level` or `full_dag` means. There was no way to say "I want characters and events, but skip relationships."

**Root cause:** `ImportWorkflow.tsx` hardcoded 4 radio options mapping directly to `W1PromptProfile` enum values, with no preset → config mapping layer.

### Problem 2: Flash/Claude model billing always unavailable

`_DEFAULT_PRICE_TABLE` in `w1_run_events.py` only covered models present when the file was first written. `appSettingsService.ts` ships default model profiles for `deepseek-v4-flash` and `deepseek-v4-pro`. The orchestrator's default model (`claude-sonnet-4-6`) also had no entry. These all fell through to `cost_unavailable_reason`.

**Root cause:** Price table was not kept in sync with app-level model defaults.

---

## Changes Made

### Backend: `sidecar/workflows/w1_run_events.py`

Added/corrected 4 entries in `_DEFAULT_PRICE_TABLE`:

| Alias key | Input $/1M | Output $/1M | Matches model strings |
|-----------|-----------|------------|----------------------|
| `deepseek-v4-flash` | 0.14 | 0.28 | `deepseek-v4-flash` |
| `deepseek-v4-pro` | 0.435 | 0.87 | `deepseek-v4-pro` |
| `claude-sonnet-4` | 3.00 | 15.00 | `claude-sonnet-4-6`, `claude-sonnet-4-*` |
| `claude-opus-4` | 15.00 | 75.00 | `claude-opus-4-*` |

Existing longest-match-wins sort handles precedence automatically: `deepseek-v4-flash` (len 17) wins over `deepseek-v4-pro` (len 15) for any string containing both substrings.

DeepSeek V4 prices were corrected during fixback from the official DeepSeek pricing page (`https://api-docs.deepseek.com/quick_start/pricing`) after Codex acceptance review caught the initial copied V3/R1 values.

### Backend: `sidecar/models/state.py`

Added 3 optional boolean fields to `ImportGranularityProfile` (TypedDict, total=False):
- `extract_relationships: bool`
- `extract_world: bool`
- `extract_timeline: bool`

All are optional for backward compatibility with existing callers.

### Frontend: `src/ui-react/services/electronApi.ts`

Extended `W1CustomProfileConfig` with 3 optional boolean fields:
```typescript
extract_relationships?: boolean;
extract_world?: boolean;
extract_timeline?: boolean;
```

### Frontend: `src/ui-react/store.ts`

Added defaults `true` for all three extraction toggle fields in `defaultW1CustomProfileConfig`.

### Frontend: `src/ui-react/components/ImportWorkflow.tsx`

**Replaced** the mode radio buttons + profile dropdown (4 options, no context) **with:**

1. **`IMPORT_PRESETS` constant** — 8 named presets, each carrying `label`, `description`, `importMode`, `profile`, and `configOverrides`:

| Preset key | Label | Import mode | Profile |
|-----------|-------|-------------|---------|
| `auto` | Auto (Orchestrator decides) | import_all | balanced |
| `sparse_turning_points` | Sparse turning points | import_all | custom |
| `chapter_level` | Chapter-level | import_all | custom |
| `scene_level` | Scene-level | import_all | custom |
| `character_rich` | Character-rich | import_all | custom |
| `relationship_light` | Relationship-light | import_all | custom |
| `manuscript_focused` | Manuscript-focused | import_content_only | fast |
| `advanced` | Advanced (custom) | import_all | custom |

2. **Preset picker list** with `data-testid="preset-{key}"` and active highlight (border-brand).

3. **Extraction toggles** (hidden for `manuscript_focused`): Manuscript (always on, disabled), Relationships, World Model, Timeline — each mapped to `W1CustomProfileConfig` extraction fields.

4. **Advanced expert panel** gated on `activePreset === 'advanced'` — all 9 existing knobs preserved exactly, now only shown when the user explicitly wants manual control.

---

## Tests Added

### Unit: `tests/test_w1_token_ledger.py` (+4 tests, 9→13)

| Test | Asserts |
|------|---------|
| `test_deepseek_v4_flash_has_known_cost` | `cost_usd ≈ 0.14` for flash model |
| `test_claude_sonnet_4_6_has_known_cost` | `cost_usd ≈ 3.00` for `claude-sonnet-4-6` via prefix match |
| `test_unknown_model_still_unavailable_after_alias_additions` | `cost_unavailable_reason` present for unknown model |
| `test_deepseek_v4_flash_price_distinct_from_pro` | Flash 0.14 ≠ Pro 0.435 (longest-match correctness) |

### E2E: `tests/e2e/p1/import_token_cost.spec.ts` (+2 tests, 5→7)

| Test | Asserts |
|------|---------|
| `shows known cost for flash model fixture` | `cost_usd` present → `$` shown, no "unavailable" text |
| `shows unavailable reason for unrecognized model — never $0` | reason string shown, `$0` never displayed |

### E2E: `tests/e2e/p1/import_workflow_presets.spec.ts` (new, 9 tests)

| Test | Asserts |
|------|---------|
| `shows all 8 named preset options` | All labels visible in preset list |
| `auto preset is active by default` | `border-brand` on auto button |
| `selecting sparse_turning_points highlights it and deselects auto` | Brand border swaps |
| `selecting sparse_turning_points sends custom profile to w1:start` | IPC payload: `prompt_profile=custom`, `event_density=arc_level` |
| `selecting manuscript_focused sends import_content_only mode` | IPC payload: `import_mode=import_content_only` |
| `extraction toggles hidden for manuscript_focused preset` | Toggles not visible |
| `extraction toggles visible for non-manuscript presets` | Toggles visible and checked |
| `unchecking extract_relationships sends false in payload` | IPC payload: `extract_relationships=false` |
| `advanced preset shows expert panel knobs` | Expert panel hidden by default, visible after click |

---

## Remaining Assumptions

| Item | Status |
|------|--------|
| `deepseek-v4-flash` / `deepseek-v4-pro` prices | Corrected from official DeepSeek V4 pricing during fixback; re-check periodically if provider pricing changes |
| `claude-sonnet-4` price | $3/$15 per 1M configured for Sonnet 4-class aliases; re-check periodically if provider pricing changes |
| `claude-opus-4` price | $15/$75 per 1M configured for Opus 4-class aliases; re-check periodically if provider pricing changes |
| Extraction toggles backend wiring | Now fully wired — see Fixback section below |

---

## Fixback (2026-06-06)

Codex acceptance review found 5 issues. All resolved.

### Issue 1: Extraction toggles not propagating to IPC payload

**Root cause (two layers):**
- `store.ts:1857` gated `custom_profile_config` on `w1PromptProfile === 'custom'`, sending `undefined` for all other profiles (Auto uses `balanced`), silently discarding toggle values.
- `workflows.py:481` independently gated `profile_config` on `body.prompt_profile == "custom"`, blocking the router even if the store sent the data.

**Fix:**
- `store.ts`: For non-custom profiles, always send a `custom_profile_config` object containing at least the three extraction toggle fields (cast as `W1CustomProfileConfig`).
- `workflows.py`: `profile_config` is now built from the union of all `extract_*` keys from `custom_profile_config` plus the full config when profile is custom. This is an additive merge that preserves all previous custom-mode behavior.
- `ImportWorkflow.tsx`: Added `handleExtractionToggle()` — when a toggle is changed from any non-Advanced preset, the active preset auto-promotes to Advanced and `prompt_profile` switches to `custom`, so the full config (with the toggled value) is always included in the payload.

### Issue 2: Extraction toggles not wiring to backend nodes

**Root cause:** `run_streaming()` in `w1_import.py` built `initial_state` without reading `extract_relationships/world/timeline` from `profile_config`. The three post-chunk nodes had no guard.

**Fix:**
- Added `extract_relationships`, `extract_world`, `extract_timeline` to `ImportState` in `state.py`.
- `run_streaming()` now reads these from `config["profile_config"]` (defaulting `True`).
- `node_synthesize_relationships`, `node_architect_timeline`, `node_infer_world_settings` each have an early-return skip guard: if the corresponding toggle is `False`, they return empty output and emit a `phase=skip` activity event.

### Issue 3: Wrong DeepSeek V4 prices

**Root cause:** Initial W2 pass copied `deepseek-chat` prices (0.27/1.10) for flash and `deepseek-r1` prices (0.55/2.19) for pro, rather than looking up the actual V4 pricing page.

**Fix (source: https://api-docs.deepseek.com/quick_start/pricing):**

| Model | Input $/1M (before) | Output $/1M (before) | Input $/1M (after) | Output $/1M (after) |
|-------|--------------------|--------------------|-------------------|-------------------|
| `deepseek-v4-flash` | 0.27 | 1.10 | **0.14** | **0.28** |
| `deepseek-v4-pro` | 0.55 | 2.19 | **0.435** | **0.87** |

Unit tests updated to match corrected values (`test_deepseek_v4_flash_has_known_cost`: ≈0.14; `test_deepseek_v4_flash_price_distinct_from_pro`: flash ≈0.14, pro ≈0.435).

### Issue 4: UI clarity when overriding Auto preset

**Fix:** `handleExtractionToggle()` auto-promotes `activePreset` to `'advanced'` and `w1PromptProfile` to `'custom'` whenever the user changes a toggle from any non-Advanced preset. The preset list immediately highlights Advanced, making the active state unambiguous.

### Issue 5: Report corrections

This section replaces the "future-only" claim in Remaining Assumptions. Extraction toggle backend wiring is now complete. Claude/Opus pricing is still estimated until Anthropic publishes official Claude 4 pricing.

### Verification (Fixback)

| Suite | Before | After |
|-------|--------|-------|
| `test_w1_token_ledger.py` | 13/13 | **13/13** |
| `import_workflow_presets.spec.ts` | 8/9 | **9/9** |
| `import_token_cost.spec.ts` | 7/7 | **7/7** |
| `ui:build` | pass | **pass** |
