# W1 Reviewer-Ready Orchestrator Report

**Updated:** 2026-07-14

**Branch:** `main`

**Verdict:** Reviewer-ready and merged through PR #2. No known P0/P1 remains. The production-code replay of the final Flash artifact passes every diagnostic threshold; V4 Pro was attempted once but waived as an external latency gate after producing no settled call, token, or charge in 12 minutes.

## Product outcome

| User requirement | Delivered behavior | Evidence |
|---|---|---|
| Chapter splitting | The LLM returns boundaries/summary/beats/evidence; canonical chapter text is rebuilt from verified source spans. Proposal-pending imports do not write canonical chapters. | 10 staged chapters, 10 chapter nodes, 10 scene nodes, all span/hash gates green. |
| Manuscript vs Chapter | Chapter remains the source-backed content unit; Manuscript is a chapter/scene outline projection created only after package acceptance. | Staged projection is `10/20/10`; canonical projection remains empty before acceptance by design. |
| Character quality | Cross-window name canonicalization, field-level merge decisions, background/experience evidence binding, duplicate removal, and frontend experience rows. | Duplicate names `0`; 韩立/墨大夫/张铁 profile regressions; replayed profile gaps `0`. |
| Chinese tags and relationships | Chinese tag normalization and relationship allowlist; event/trait phrases are rejected as relationship types. | English/illegal tags `0`; invalid relationship types `0`. |
| World Model | Stable Notebook/Folder/Item routing with `parentId`; people, events, timeline, relationship graph, and cultivation misclassification are filtered at the final organizer boundary. | World contamination `0`; person/event organization pollution `0`; cultivation misclassification `0`. |
| Context menus | Typed command registry and clipboard; object-aware create/copy/cut/paste/rename/move/merge/archive/delete; disabled reasons, keyboard navigation, viewport clamping, and focus restoration. | P0/P1 browser coverage plus Electron runtime context-menu assertion. |
| Undo and drag | User actions commit one `UndoTransaction`; timeline/world/graph mutations preserve reference integrity and undo as one step. | Global undo, timeline drag, graph transaction, and world container deletion regressions pass. |
| Electron safety | Renderer uses preload/context isolation; project root and portrait paths are authorized; symlink escapes are rejected. | Electron runtime smoke passes bridge, source-grant, symlink, context-menu, and project-service checks. |
| Long-running AI feedback | Streaming activity events, 15-second heartbeat artifact, usage ledger, cancellation cleanup, and inner/outer hard timeouts. | Heartbeat observed during live runs; budget/cancellation tests pass; no six-hour silent run is possible under the runner. |

## Architecture decision

W1 remains an **orchestrated pipeline**, not an unconstrained ReAct loop. The model may choose bounded tools, local reruns, and stop conditions; deterministic code still owns source integrity, proposal atomicity, budgets, validation, and persistence. This preserves useful model autonomy without allowing an LLM to bypass cost or data-safety gates.

Import authority is now singular:

1. Electron/UI starts one W1 sidecar import package.
2. Sidecar stages source-backed proposals and a dependency DAG.
3. Workbench accepts/rejects/retries one package atomically.
4. Only accepted packages update canonical project state.
5. Every user mutation is represented as a command/transaction that can be undone.

## Final verification

| Gate | Result |
|---|---|
| Full W1 backend suite | **659 passed in 9.92s** |
| Full P0/P1 Playwright | **230 passed in 4.7m** |
| UI lint | **Passed**, zero warnings |
| UI production build | **Passed**; Vite reports only the known large-chunk optimization warning |
| Electron runtime smoke | **Passed in 9.7s**; all assertions completed before expected forced close fallback |
| Python compileall | **Passed** |
| `git diff --check` | **Passed** |
| Secret scan | No real API key found; only explicit redaction test fixtures matched |
| Replayed W1 diagnostics | **Exit 0 with every symptom flag false** |
| Independent low-cost reviewer | **No P0/P1 findings**; 246 targeted backend/security tests and Electron syntax checks passed |

### Final Flash artifact

- Source artifact: `/tmp/narrative_ide_w1_live_smoke/20260713_033431`.
- Model: `deepseek-v4-flash`; elapsed `668s`; `36` calls.
- Usage: `274090` input tokens, `101153` output tokens, `$0.066695`.
- Native artifact passed source, proposal, evidence, dedupe, tags, relationships, World, timeline, usage, budget, and secret gates.
- Its only failure was an empty 张铁 `experience` row at the final serializer boundary.
- Exact inbox replay through the repaired production serializer recovered two evidence-bound experiences without another provider call.
- A copied replay project at `/tmp/narrative_ide_w1_live_smoke/20260714_replay_033431_project` passes `tools/w1_import_diagnostics.py --fail-on-threshold` with all symptom flags false.

### Paid-run ledger

- Six ledger-backed Flash runs cost **$0.439420 total**. The first pre-ledger exploratory run is not included because it had no trustworthy settled ledger.
- A single V4 Pro attempt started at `/tmp/narrative_ide_w1_live_smoke/20260714_000251` with a `$8` cap and 30-minute deadline.
- After 12 minutes its first request still showed `0` settled calls, `0` tokens, and `$0`; it was stopped because the remaining deadline could not complete the extraction graph.
- The interruption exposed and fixed an un-awaited coroutine cancellation defect. Budgeted extraction now creates prompts lazily, and the new cancellation regression passes.
- No additional paid retry is recommended: it would test provider latency more than repository correctness.

## Residual P2 risks

- Reviewer metadata still reports 15 `character_thin_card` warnings. They are non-blocking because the import intentionally creates evidence-backed draft cards instead of hallucinated dossiers; later enrichment workflows own deeper biography.
- The Vite bundle is about 1.46 MB before gzip. Code splitting is a performance optimization, not a W1 correctness blocker.
- Electron's normal close can be delayed by the intentional unsaved-change prompt; the smoke harness verifies all behavior, then force-terminates only during cleanup.
- A complete provider-side V4 Pro run remains unobserved because of external response latency. Flash plus deterministic replay is the accepted evidence for this candidate.
- Cancellation propagates between extraction stages and is bounded by the runner's outer process timeout; a provider SDK that ignores task cancellation can still require that forced process termination.
- `tests/e2e/p1/backlog_gaps.spec.ts` was intentionally replaced by `backlog_story_gaps.spec.ts`, which keeps the two behaviors while adding a deterministic fixture and route assertion.

## Git closure

- Reviewer-ready implementation commit: `f2d18e5`.
- Integration PR: [#2](https://github.com/migodam/Fiction_Writer/pull/2), merged with commit `48bd705`.
- Canonical branch: `main`; local and remote checks resolve to the same merge commit before this documentation follow-up.
- Every historical local/remote branch tip and detached worktree commit was verified as an ancestor of `origin/main` before cleanup.
- All historical worktrees were clean and removed. All merged local and remote branches were deleted.
- Retained immutable tags: `backup/w1-pre-reviewer-ready-20260711` and `release/w1-reviewer-ready-20260714`.
- Git history was preserved; no destructive reset or squash was used.

## 2026-07-14 post-gate hotfix

The first real Workbench package acceptance exposed a contract gap that the earlier diagnostics did not cover: Organizer items referenced `world_container_*`, but both supervisor paths dropped Organizer containers and proposal writing emitted fallback `cont_import_*` containers. The package therefore blocked on `prop_56589c5c2063` even though pre-acceptance quality flags were false.

The hotfix propagates Organizer containers, validates/rebinds World parent references at the final proposal boundary, and adds hard diagnostics for dangling World references and stale package block markers. The preserved 10-chapter artifact was repaired without another provider call. Post-fix evidence: `158` related Python tests, UI build/lint, and `22/22` Workbench package Playwright tests pass; the artifact now reports all diagnostic flags false with dangling references `48 -> 0` and stale block markers `65 -> 0`.
