# W1 Failure Closure Claude Dispatch

## Current Baseline
- Repo: `/Volumes/migodam's-external-brain/Development/Narrative_IDE`
- Branch: `codex/w1-orchestrated-import-quality`
- Latest benchmark: `benchmark_results/w1_orchestrated_import_quality_20260525_085059`
- Current benchmark status: `WARNING`
- Main blockers: proposal-write OOM, mixed Chinese/English fields, near-miss character coverage, world entity inflation, unverified chapter order.

## How To Use These Prompts
1. Open three Claude Code windows first.
2. In Claude A, paste `01_claude_p0_proposal_oom.md`.
3. In Claude B, paste `02_claude_p1_language_policy.md`.
4. In Claude C, paste `03_claude_p2_quality_cost_world.md`.
5. Each prompt starts with `/plan`. Let Claude produce only a plan first.
6. Send the three Claude plans back to Codex for review before running `/goal`.
7. Only after Codex approves a Claude plan, tell that Claude window to continue with `/goal`.
8. Do not start Claude D until Codex has integrated A/B/C.

## Claude Window Order
- Wave 1 parallel: A, B, C.
- Integration: Codex only.
- Wave 2 validation: D.

## Worktree Recommendation
Use separate branches/worktrees if possible:
- Claude A: `codex/w1-closure-p0-proposal-oom`
- Claude B: `codex/w1-closure-p1-language-policy`
- Claude C: `codex/w1-closure-p2-quality-cost`
- Claude D: `codex/w1-closure-validation-benchmark`

If Claude works in the same checkout, stop before `/goal` and let Codex coordinate branch/worktree creation first.

## What Codex Will Do
- Review Claude `/plan` outputs.
- Decide whether each Claude can proceed to `/goal`.
- Integrate A -> B -> C.
- Resolve shared-surface conflicts.
- Run targeted tests.
- Give the final instruction to start Claude D.

## What Claude Must Not Do
- Do not merge main.
- Do not edit unrelated UI/product files.
- Do not update `AGENTS.md` or `CLAUDE.md` unless the prompt explicitly says so.
- Do not start the full 50-chapter benchmark until A/B/C are integrated.

