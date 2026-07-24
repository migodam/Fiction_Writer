# Workflow Status

This is the status source of truth for W0-W7. Use `FRONTEND_BACKEND_CHECKLIST.md` as the integration source of truth.

## Status Legend
- `active`: backend implemented and intended for current product use
- `ui-gap`: backend verified but current UI trigger/control surface is incomplete
- `partial`: usable path exists, but known gaps remain open
- `reference`: historical or diagnostic only

## Runtime Resilience Baseline (2026-07-21)

The current implementation adds a per-project SQLite WAL `RuntimeStore` at
`system/runtime/agent_runtime.db` for durable run/attempt, lease/fence, event,
tool-call, receipt, decision, and checkpoint-metadata records. LangGraph state
for W0-W7 is separately persisted in `system/runtime/langgraph_checkpoints.db`;
the runtime store deliberately holds metadata rather than graph-state blobs.

W1 now has stable lineage/cache identity and isolated attempt artifacts,
atomic checkpoint receipts, conservative legacy-progress recovery, runtime
recovery endpoints/IPC/UI, immutable checkpoint forks, and a provider response
recovery contract. Provider operation keys are stable and sequence-independent,
excluding `attemptId`; project-local response artifacts use content addressing
with `0700` directories and `0600` files, and verified artifacts are reusable
across attempts. Per-process singleflight prevents duplicate provider calls.
Credentials are transient and redacted before persistence. Resource fencing and
budget ceilings are durable; legacy recovery gets a fail-closed USD 3 budget if
pricing/usage is unknown. Unknown outcomes remain human-gated on cache and
network paths. The usage ledger rebuilds from unique cached operations without
double-counting within a session. Recovery Center requires an explicit
retry-once or cancel decision before any paid retry.

Durable event polling is available through the runtime API. Electron also has
an SSE bridge to legacy `/workflow/stream`, with cursor replay and polling
fallback; no separately verified `/runtime` SSE endpoint exists. API, mocked
IPC, real Electron restart recovery, disposable real-fixture acceptance, and
provider recovery are covered. The authorized Import Text 18 resume completed
10/10 with 8 calls costing `$0.014351`; all 108 proposals remain pending. The
post-run offline evidence repair passed diagnostics with every symptom flag
false. Current W1/runtime regression: **782 passed**. Exact commands and
receipts are in the 2026-07-21 dev log.

## Workflow Matrix
| Workflow | Purpose | Backend status | UI status | Current status | Integration source | Open gaps |
|---|---|---|---|---|---|---|
| W0 Orchestrator | Multi-step workflow planner/executor | Durable project checkpointer wired; automated coverage exists | Agents workspace control surface present for goal entry, status, permissions, and results | `partial` | `FRONTEND_BACKEND_CHECKLIST.md` | No live provider regression recorded for this baseline |
| W1 Import | Novel/file import into proposals and project structure | Durable attempts, provider-response recovery, legacy validation, and completed 10/10 paid recovery covered | Import modal includes Recovery Center/runtime event and checkpoint surfaces alongside import observability | `partial` | `FRONTEND_BACKEND_CHECKLIST.md` | Import Text 18 has 108 pending proposals awaiting human review; thin supporting-character cards remain non-blocking |
| W2 Manuscript Sync | Sync writing content back into canonical/project data proposals | Verified in backend | Writing Chapters trigger with status/result path to Workbench Inbox | `active` | `FRONTEND_BACKEND_CHECKLIST.md` | Proposal acceptance safety remains owned by Workbench |
| W3 Writing Assistant | Continue/rewrite/expand/improve-dialogue flows | Verified and wired | Available in writing flows | `active` | `FRONTEND_BACKEND_CHECKLIST.md` | Occasional preamble text still needs prompt hardening |
| W4 Consistency Check | Detect contradictions and consistency issues | Verified and wired | Audit button and polling present | `active` | `FRONTEND_BACKEND_CHECKLIST.md` | Issue review/queue-fix closure still lighter than target product loop |
| W5 Simulation | Scenario/reviewer-style simulation engines | Verified and wired | Triggered from Simulation workspace | `active` | `FRONTEND_BACKEND_CHECKLIST.md` | Engine UX still scaffold-level in places |
| W6 Beta Reader | Persona-based reading feedback | Verified and wired | Triggered from Beta Reader workspace | `active` | `FRONTEND_BACKEND_CHECKLIST.md` | Persona authoring and comparative review need more product closure |
| W7 Metadata Ingestion | Reference library ingestion and style grounding | Verified and wired | Metadata workspace supports import and status | `active` | `FRONTEND_BACKEND_CHECKLIST.md` | Style extraction quality still uneven for some genres |

## World Model and semantic review (2026-07-25)

The World Model now projects a stable Notebook/Folder/Item tree using `folderId` ownership.
Legacy `categoryPath` inference is not a runtime grouping rule. W1 emits a candidate ledger and
semantic relocation plans; ambiguous candidates are quarantined, and all changes stop at the
package proposal gate before canonical acceptance.

The accepted-project reconcile tool is dry-run by default and creates a backup and receipt when
applied. The 2026-07-14 benchmark moved from 1 semantic error and 19 linkage warnings to 0/0 in
the offline audit: 9 event-scene links, 13 event-world links, 7 scene-world inverse links, 10
high-confidence reclassifications, and 2 quarantined candidates. This is not a new paid run.

## Agent execution surface (2026-07-25)

Agent Dock projects durable execution into plan, agent, tool call/result, review, approval,
artifact, checkpoint, error, and result states. It shows auditable summaries, progress, cost, and
human actions without exposing hidden chain-of-thought. Research references live in
`communication/2026-07-25-agent-harness-open-source-architecture-research.md`.

Concrete World-to-event deep links now select the event and branch, show a title/time/branch
focus banner, center and highlight the event once, and preserve later manual panning. This path
is committed and verified in Playwright plus an actual 1280px browser pass.

## Current Product Gaps That Are Real
- W2 now has a canonical Writing Chapters trigger and status/result path; proposal acceptance safety remains a Workbench closure item.
- W0 now has a canonical Agents workspace control surface for goal composition, permissions, status, and results.
- Proposal acceptance now blocks unsupported canonical operations instead of accepting no-ops; dedicated link/unlink canonical mutators remain future work.
- Publish/export remains present as a workspace but is not yet a fully closed delivery surface.
- Sidecar lifecycle now has durable runtime/checkpointer shutdown handling and restart lease invalidation. Real Electron restart recovery and the paid Import Text 18 resume pass; the remaining gate is human review of the pending package.

## Workflow Ownership Boundaries
- Status changes update this file.
- Bridge/action wiring changes update `FRONTEND_BACKEND_CHECKLIST.md`.
- Deep workflow implementation details remain in code and `langgraph.md`, which is reference-only.

## W0 UI Control Surface Notes
- Entry point: Agents activity (`/agents/console`), `W0 Orchestrator` panel above Agent Chat.
- User path: compose goal -> start W0 -> watch plan/progress/status -> grant or deny permission if the sidecar returns `waiting_permission` -> read completion or error card.
- Status source: Zustand orchestrator state backed by `orchestrator:start`, `orchestrator:status`, `orchestrator:grant`, and `orchestrator:deny`.
- 2026-04-24 WS-02 scoped W0 fix: child workflows that return `done`/`completed` directly from their start endpoint are marked completed immediately instead of being polled into a false timeout/failure.

## W1 UI Observability Notes
- Activity events and chunk logs are merged by timestamp into one stable execution stream; the UI no longer renders two competing reverse-ordered lists.
- The running surface separates the current action from historical output and keeps stage, extraction counts, API concurrency, token/cost usage, elapsed time, idle warnings, and budget exhaustion visible.
- The idle surface uses compact presets plus an explicit extraction scope instead of a long single-column setup form.
