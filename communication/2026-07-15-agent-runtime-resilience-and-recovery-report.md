# Narrative IDE Agent Runtime Resilience and Recovery Report

**Final implementation review:** 2026-07-21
**Branch:** `codex/agent-runtime-resilience`
**Backup tag:** `backup/agent-runtime-pre-resilience-20260715` (`c9598dc`)

## Executive Verdict

The durable Agent Runtime implementation is reviewer-ready. Automated backend,
frontend, Electron lifecycle, crash recovery, real-fixture acceptance,
original benchmark migration, paid provider recovery, and offline artifact
repair gates pass. The current W1/runtime suite is **782 passed**.

Import Text 18 completed its authorized 10/10 DeepSeek V4 Flash resume for
`$0.014351`. The resulting 108-proposal package passes all diagnostic hard
thresholds and remains entirely pending for human review.

## What Shipped

### Durable Runtime

- Project-scoped SQLite WAL runtime for runs, attempts, leases, fencing, events,
  tool intents/results, artifact receipts, human decisions, outbox, durable task
  DAGs, dead letters, and bounded memory records.
- Separate SQLite LangGraph checkpointers for W0-W7; no `MemorySaver` dependency
  remains on the production path.
- Stable `lineageId`, unique `attemptId`, thread/checkpoint identity, and
  content-addressed cache keys.
- Provider response operation keys are stable and sequence-independent and
  exclude `attemptId`; project-local content-addressed response artifacts use
  `0700` directories and `0600` files. Verified artifacts are reusable across
  attempts, per-process singleflight prevents duplicate calls, and usage is
  rebuilt from unique cached operations without session double counting.
- Transactional cold-start reconciliation: running attempts become
  `interrupted`; unfinished provider intents become `unknown_outcome`; completed
  results stay immutable.
- Durable pause, cancel, resume, fork, and retry-once/cancel human decisions.

### W1 Recovery And Agent Control

- Verified legacy 4/10 checkpoint migration with source/hash/version validation.
- Attempt-isolated artifacts and conservative cache reuse; untrusted 4-9 legacy
  chunks are not reused.
- Provider calls record intent before I/O and result after I/O. Unknown outcomes
  require explicit human authorization and are never auto-retried.
- Deterministic safety shell with bounded typed Planner, Self-Ask, Plan-Execute,
  and ReAct metadata. Parallel extraction is allowed; canonical commit remains a
  single-writer operation.
- Budget ceilings cannot increase on resume; missing usage and unknown pricing
  fail closed.
- Unknown outcomes remain human-gated on both cache and network paths.

### Package And File Durability

- `ArtifactRef/v2` uses relative path, SHA-256, contract version, lineage, and
  attempt. Absolute project paths are no longer authoritative.
- Project-root containment, traversal, symlink, source hash, artifact hash, and
  lineage/attempt checks remain mandatory.
- Package acceptance uses a write-ahead transaction with preimages, postimages,
  commit marker, idempotent recovery, and stale chapter/scene tombstones.
- Repair and Accept are separate actions. Repair never changes canonical data;
  Accept remains an explicit package-scoped user action.

### Electron And UI

- Recovery Center shows interrupted runs, compatible source, completed/remaining
  chunks, unknown calls, budget state, and explicit retry/cancel choices.
- Durable event replay uses monotonic sequence and Last-Event-ID semantics with
  polling fallback; the Import console shows a single chronological execution
  chain rather than disconnected chunk cards.
- Checkpoint timeline supports immutable child attempts for Time Travel.
- Multi-Agent panel shows DAG ownership, dependencies, waiting reasons, and
  writer locks without displaying hidden reasoning.
- Sidecar startup is health-gated and deduplicated. Shutdown drains streams,
  databases, and sidecars before a bounded Electron 30 exit fallback.

## Real Data Results

### Original Benchmark Repair-Only Migration

`benchmark_results/w1_reviewer_ready_final_20260714` was migrated in place after
verification against the immutable backup.

- Before: inbox SHA-256 `7390b1de...08bb6`; staged projection `dcd8c6c4...03912`.
- After: inbox SHA-256 `a8b87bcb...b61935d`; staged projection `0846b90d...ff25f5`.
- Result: `89` pending, `0` accepted, `0` proposal history.
- All canonical character, chapter, scene, timeline, World, and manuscript hashes
  were identical before and after.
- Restart preserved ArtifactRef v2 and the explicit Accept action.
- Receipt: `benchmark_results/_evidence/20260715_w1_original_repair_only/repair-only-receipt.json`.

### Disposable Benchmark Acceptance

The real 89-proposal fixture copy completed Repair, explicit Accept, and restart
persistence with exact counts:

| Entity | Count | Entity | Count |
| --- | ---: | --- | ---: |
| Characters | 20 | Character tags | 5 |
| Relationships | 2 | Chapters | 10 |
| Scenes | 10 | Manuscript nodes | 20 |
| Timeline branches | 1 | Timeline events | 9 |
| World containers | 7 | World items | 24 |

Latest evidence root:
`/tmp/narrative-ide-w1-actual-fixture-1784300243138/`.

### Import Text 18 Paid Recovery

- Source SHA-256 remained
  `6c7cfd49949e89cecb8b00a4bd9ab374e7393ff1b4fe84a0e8a809e060cb522d`.
- DeepSeek `/models` authentication probe returned HTTP `200` without sending
  manuscript text.
- The user explicitly authorized the first 10 chapters for `deepseek-v4-flash`
  with a USD 3 hard ceiling.
- Durable reconciliation recovered the prior verified response, and run/task
  heartbeats prevented both run-lease and DAG task-claim expiry.
- The attempt completed 10/10 chunks and all 16 DAG tasks: 8 accounted calls,
  35,805 input tokens, 33,351 output tokens, `$0.014351` total cost.
- Output: 108 pending proposals, 10 staged chapters, 20 manuscript nodes, and
  10 scene documents. No proposal was accepted automatically.
- Deterministic offline repair bound 27 characters and 5 events to source
  evidence, restored supported background/experience, and removed 3 empty
  branches. It made zero provider calls.
- Repair receipt:
  `system/imports/lineage_68b3fe6d3172718a45f6ca66/attempts/legacy_attempt_614123c9b409771fcdf06f0c/repair_receipts/20260721T034616Z/receipt.json`.
- Final diagnostics exited 0 with every symptom flag false.

### Zero-Cost Provider Recovery Verification

- Restart coverage reused five saved role responses and called the provider only
  for the sixth missing role.
- Verified response reuse worked across attempts using the stable operation key.
- Per-process singleflight and session usage-ledger deduplication passed.
- Cache-path and network-path `unknown_outcome` states remained human-gated.

## Verification Matrix

| Gate | Result |
| --- | --- |
| W1/runtime pytest | **782 passed** in 7.89s |
| W1 package/recovery/SSE/transaction Playwright | **44 passed** in 11.1s |
| Current targeted recovery/transaction Playwright | **7 passed** in 4.7s |
| UI lint | **PASS**, zero warnings |
| UI production build | **PASS** |
| Electron runtime smoke | **PASS**, clean exit |
| Electron sidecar lifecycle | **PASS** |
| Real disposable fixture | **PASS**, 89 accepted and restart-persistent |
| Original benchmark repair-only | **PASS**, 89 pending and canonical hashes unchanged |
| Zero-cost provider response recovery | **PASS**, 5 saved roles reused; 1 missing role called |
| Real Import Text 18 paid 10/10 completion | **PASS**, `$0.014351` under `$3` cap |
| Real Import Text 18 proposal diagnostics | **PASS**, every symptom flag false; 108 pending |

## Remaining Risks

- The monolithic legacy E2E suite currently reports 250/270 passing. The current
  dedicated W1 recovery, SSE, observability, and package-acceptance gate passes
  44/44; the 20 residual failures are old unscoped fixtures and cross-workspace
  smoke selectors that need a separate compatibility/test-maintenance pass.
- A provider-level per-request timeout shorter than the 20-minute workflow fuse
  should be considered as a P2 tuning item; it must still produce an unknown
  outcome after transport ambiguity.
- The production UI bundle is 1.52 MB before gzip (439.82 kB gzip); route-level
  code splitting is a P2 performance improvement.
- The project transaction bridge has atomic journal recovery but no filesystem
  `fsync`, so it is not a formal power-loss durability guarantee.
- The selected DeepSeek provider profile reports `enabled=false` despite a valid
  selected model and successful authentication. Runtime credential resolution
  works, but Settings should normalize this state in a later cleanup.

## Human Next Step

1. Open Import Text 18 in Workbench and review the 108-proposal package.
2. Inspect the remaining non-blocking reviewer notes: 12 thin supporting
   character cards and 3 repeated-phrase suggestions.
3. Accept packages manually only after review; recovery code never crosses the
   proposal gate.

## Local Run Guide

```bash
npm install
npm run electron:dev
```

Use the Electron window as the product. For browser-only UI work:

```bash
npm run ui:dev
```

The terminal prints the local Vite URL. Native dialogs, settings, sidecar
lifecycle, Recovery Center, and package transactions require Electron.
