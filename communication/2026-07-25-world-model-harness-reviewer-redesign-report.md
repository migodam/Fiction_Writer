# World Model and Harness Reviewer Redesign

Date: 2026-07-25  
Scope: W1 semantic quality, accepted-project reconciliation, World Model UI, and Agent Dock.

## PM Verdict

The 2026-07-14 accepted-project data had 1 semantic error and 19 linkage warnings. The offline
reconcile/audit path now reports 0 errors and 0 warnings. It added 9 event-scene links, 13
event-world links, and 7 scene-world inverse links; 10 high-confidence classifications were
repaired and 2 uncertain candidates were quarantined. This was a local accepted-project repair,
not a new paid import.

The pending `Import Text 18` package was also re-reviewed offline. All 108 proposals remain
staged: 20 World candidates were rerouted or backfilled, 8 ambiguous candidates were held for
human review, and the rebuilt graph has 0 diagnostics and 0 dropped references. No canonical
entity was accepted by this migration.

## What Changed

- World navigation is a stable `Notebook -> Folder -> Item` tree. `folderId` is canonical;
  display names and `categoryPath` do not infer placement.
- W1 records a candidate ledger, semantic reviewer decision, organizer relocation plan, and
  staged proposal. Canonical data remains protected by the package acceptance gate.
- Character-like World candidates such as `正门主王六` can be merged into `王六` with aliases,
  role, and evidence. Ambiguous candidates are quarantined instead of forced into `门派组织`.
- Accepted-project reconciliation is dry-run by default, creates a backup/receipt on apply, and
  repairs evidence links without calling an external model.
- Pending-package semantic migration now uses a prepared receipt, content-hashed staged payloads,
  and automatic roll-forward/rollback recovery across `inbox.json` and `proposal_graph.json`.
- Package-scoped proposals cannot be accepted through the single-proposal service path. Even a
  direct store call is blocked; acceptance must use the complete package transaction.
- Blank template writing is removed only when chapter, scene, summary, goal, notes, links, and
  status still match known blank-template defaults. Dynamic IDs are supported without deleting
  authored placeholders.
- Agent Dock presents normalized durable execution states: plan, agent, tool call/result, review,
  approval, artifact, checkpoint, error, and result. It shows auditable summaries rather than
  hidden chain-of-thought or an unstructured token stream.

## Evidence and Boundaries

Implementation commits since `62a129f` include semantic review, direct-graph relocation,
accepted-project reconcile, World folder UI, and Agent execution surface changes. Detailed
Claude Code/Codex public-source research is kept in
`communication/2026-07-25-agent-harness-open-source-architecture-research.md`.

Concrete Timeline deep-link focus is committed and verified. The actual browser path from
`Glass Bridge` to `Bridge Intercept` shows the event title, time, branch, centered focus ring,
and keeps the right-side Agent Dock readable at 1280px.

The headed Electron actual-fixture gate was rerun. It selected a real copied project, repaired
and explicitly accepted its 89-proposal package, persisted the result, restarted Electron,
verified acceptance persistence, then opened the interrupted W1 recovery fixture and inspected
its durable run/events. The complete gate passed in 17.6 seconds. Project selection and first
load completed in about 0.5 seconds in the isolated run.

Computer Use against an older, already-running development window timed out while reading the
accessibility tree after choosing the original 46 MB `Import Text 18` project. This did not
reproduce in the clean Electron actual-fixture process, so it is recorded as a desktop automation
observation rather than a confirmed product-load defect.

## Verification

- Active W1/runtime pytest selection: `817 passed`.
- Full repository pytest: `842 passed`, with `11 failed + 7 errors` isolated to reference-only
  V2/V3 `src/core/ProjectMemory` tests and missing `tests/api_key.txt`.
- UI lint and production build: passed.
- Full P0/P1 Playwright: `276 passed`; the near-threshold timeline gesture was then repeated five
  times (`15 passed`) with a larger unambiguous drag gesture.
- Package/relocation/writing focused Playwright: `39 passed`.
- World/Agent responsive and interaction Playwright: passed.
- Timeline/World/Agent deep-link Playwright: passed.
- Accepted benchmark semantic audit after migration: `0 errors / 0 warnings`.
- Electron actual-fixture: passed (89-proposal repair/accept, persistence after restart, interrupted
  W1 recovery, screenshot and migration receipt).
- Electron runtime smoke: passed; bridge, permission guards, context menu, symlink rejection, and
  project service checks completed in 7.1 seconds.
- Actual browser: World detail readable with Agent Dock open; concrete event centered and labeled.

## Next Gate

Retain the reconcile receipts and audit output with release evidence, then merge/push the branch.
The 8 held `Import Text 18` candidates intentionally remain a human review gate; accepting them
without a semantic decision is not a valid completion path.
