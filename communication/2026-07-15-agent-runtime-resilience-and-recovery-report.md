# Narrative IDE Agent Runtime Resilience and Recovery Report

**Final implementation review:** 2026-07-17
**Branch:** `codex/agent-runtime-resilience`
**Backup tag:** `backup/agent-runtime-pre-resilience-20260715` (`c9598dc`)

## Executive Verdict

The durable Agent Runtime implementation is reviewer-ready. Automated backend,
frontend, Electron lifecycle, crash recovery, real-fixture acceptance, and
original benchmark repair-only migration gates pass.

The real Import Text 18 paid recovery is intentionally **waiting for a human
decision**, not marked complete. Five of six DeepSeek calls returned; one call
remained unresolved until the 20-minute runner fuse stopped the process. Cold
start converted that single unfinished intent to `unknown_outcome`, preserved
the trusted 4/10 checkpoint, and prohibited automatic retry.

## What Shipped

### Durable Runtime

- Project-scoped SQLite WAL runtime for runs, attempts, leases, fencing, events,
  tool intents/results, artifact receipts, human decisions, outbox, durable task
  DAGs, dead letters, and bounded memory records.
- Separate SQLite LangGraph checkpointers for W0-W7; no `MemorySaver` dependency
  remains on the production path.
- Stable `lineageId`, unique `attemptId`, thread/checkpoint identity, and
  content-addressed cache keys.
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
- One explicit `deepseek-v4-flash` resume was issued with a USD 3 hard ceiling.
- Six remaining calls were dispatched; five produced durable result receipts.
- The sixth did not return before the 20-minute hard fuse. No seventh call or
  retry was issued.
- Checkpoint stayed at the last atomic boundary: 4/10 and four extractions.
- Cold restart produced `interrupted`, five `result`, one `unknown_outcome`, and
  one pending human decision.
- Failure receipt:
  `/Users/migodam/narrative-ide-recovery-receipts/import-text18-2026-07-17T14-30-28-317Z/failure.json`.

No accurate cost can be claimed for the partial batch because the node did not
commit its usage ledger. Recovery therefore reports unknown spend and cannot
resume until the user explicitly chooses retry-once or cancel.

## Verification Matrix

| Gate | Result |
| --- | --- |
| W1/runtime/agentic/checkpointer pytest | **781 passed** in 7.93s |
| W1 package/recovery/SSE/transaction Playwright | **44 passed** in 11.1s |
| UI lint | **PASS**, zero warnings |
| UI production build | **PASS** |
| Electron runtime smoke | **PASS**, clean exit |
| Electron sidecar lifecycle | **PASS** |
| Real disposable fixture | **PASS**, 89 accepted and restart-persistent |
| Original benchmark repair-only | **PASS**, 89 pending and canonical hashes unchanged |
| Real Import Text 18 cold-start reconcile | **PASS**, 1 unknown call human-gated |
| Real Import Text 18 10/10 completion | **WAITING FOR HUMAN DECISION** |

## Remaining Risks

- The unresolved DeepSeek call requires an explicit retry-once or cancel choice.
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

1. Open Import Text 18 and enter **Import > Recovery Center**.
2. Inspect the single unknown DeepSeek call and unknown-spend warning.
3. Choose **Retry once** to authorize exactly one replacement call, or **Cancel**
   to preserve 4/10 without further cost.
4. After retry, run the paid resume runner again. It will still enforce USD 3,
   one Resume, 20 minutes, 10/10 contiguous checkpoint, and zero accepted
   proposals.
5. Review and Accept the resulting proposal package manually; no recovery code
   is allowed to cross that gate.

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
