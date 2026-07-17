# Workflow Status

This is the status source of truth for W0-W7. Use `FRONTEND_BACKEND_CHECKLIST.md` as the integration source of truth.

## Status Legend
- `active`: backend implemented and intended for current product use
- `ui-gap`: backend verified but current UI trigger/control surface is incomplete
- `partial`: usable path exists, but known gaps remain open
- `reference`: historical or diagnostic only

## Runtime Resilience Baseline (2026-07-15)

The current implementation adds a per-project SQLite WAL `RuntimeStore` at
`system/runtime/agent_runtime.db` for durable run/attempt, lease/fence, event,
tool-call, receipt, decision, and checkpoint-metadata records. LangGraph state
for W0-W7 is separately persisted in `system/runtime/langgraph_checkpoints.db`;
the runtime store deliberately holds metadata rather than graph-state blobs.

W1 now has stable lineage/cache identity and isolated attempt artifacts,
atomic checkpoint receipts, conservative legacy-progress recovery, runtime
recovery endpoints/IPC/UI, and immutable checkpoint forks. Credentials are
transient and redacted before persistence. Resource fencing and budget ceilings
are durable; legacy recovery gets a fail-closed USD 3 budget if pricing/usage is
unknown. Tool calls can be recorded as `unknown_outcome`; Recovery Center
requires an explicit retry-once or cancel decision before any paid retry.

Durable event polling is available through the runtime API. Electron also has
an SSE bridge to legacy `/workflow/stream`, with cursor replay and polling
fallback; no separately verified `/runtime` SSE endpoint exists. API, mocked
IPC, real Electron restart recovery, and disposable real-fixture acceptance are
covered. A paid live-provider resume remains a separate gate. Exact commands
are in `dev_logs/2026-07-15-agent-runtime-resilience.md`.

## Workflow Matrix
| Workflow | Purpose | Backend status | UI status | Current status | Integration source | Open gaps |
|---|---|---|---|---|---|---|
| W0 Orchestrator | Multi-step workflow planner/executor | Durable project checkpointer wired; automated coverage exists | Agents workspace control surface present for goal entry, status, permissions, and results | `partial` | `FRONTEND_BACKEND_CHECKLIST.md` | No live provider regression recorded for this baseline |
| W1 Import | Novel/file import into proposals and project structure | Durable attempts, recovery, and legacy validation covered by automated tests | Import modal includes Recovery Center/runtime event and checkpoint surfaces alongside import observability | `partial` | `FRONTEND_BACKEND_CHECKLIST.md` | Disposable real-fixture acceptance and 4/10 restart recovery pass; paid live-provider resume remains open |
| W2 Manuscript Sync | Sync writing content back into canonical/project data proposals | Verified in backend | Writing Chapters trigger with status/result path to Workbench Inbox | `active` | `FRONTEND_BACKEND_CHECKLIST.md` | Proposal acceptance safety remains owned by Workbench |
| W3 Writing Assistant | Continue/rewrite/expand/improve-dialogue flows | Verified and wired | Available in writing flows | `active` | `FRONTEND_BACKEND_CHECKLIST.md` | Occasional preamble text still needs prompt hardening |
| W4 Consistency Check | Detect contradictions and consistency issues | Verified and wired | Audit button and polling present | `active` | `FRONTEND_BACKEND_CHECKLIST.md` | Issue review/queue-fix closure still lighter than target product loop |
| W5 Simulation | Scenario/reviewer-style simulation engines | Verified and wired | Triggered from Simulation workspace | `active` | `FRONTEND_BACKEND_CHECKLIST.md` | Engine UX still scaffold-level in places |
| W6 Beta Reader | Persona-based reading feedback | Verified and wired | Triggered from Beta Reader workspace | `active` | `FRONTEND_BACKEND_CHECKLIST.md` | Persona authoring and comparative review need more product closure |
| W7 Metadata Ingestion | Reference library ingestion and style grounding | Verified and wired | Metadata workspace supports import and status | `active` | `FRONTEND_BACKEND_CHECKLIST.md` | Style extraction quality still uneven for some genres |

## Current Product Gaps That Are Real
- W2 now has a canonical Writing Chapters trigger and status/result path; proposal acceptance safety remains a Workbench closure item.
- W0 now has a canonical Agents workspace control surface for goal composition, permissions, status, and results.
- Proposal acceptance now blocks unsupported canonical operations instead of accepting no-ops; dedicated link/unlink canonical mutators remain future work.
- Publish/export remains present as a workspace but is not yet a fully closed delivery surface.
- Sidecar lifecycle now has durable runtime/checkpointer shutdown handling and restart lease invalidation. Real Electron restart recovery passes; the remaining external gate is the paid provider resume.

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
