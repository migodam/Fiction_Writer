# Workflow Status

This is the status source of truth for W0-W7. Use `FRONTEND_BACKEND_CHECKLIST.md` as the integration source of truth.

## Status Legend
- `active`: backend implemented and intended for current product use
- `ui-gap`: backend verified but current UI trigger/control surface is incomplete
- `partial`: usable path exists, but known gaps remain open
- `reference`: historical or diagnostic only

## Workflow Matrix
| Workflow | Purpose | Backend status | UI status | Current status | Integration source | Open gaps |
|---|---|---|---|---|---|---|
| W0 Orchestrator | Multi-step workflow planner/executor | Verified in sidecar | No dedicated production control surface yet | `ui-gap` | `FRONTEND_BACKEND_CHECKLIST.md` | Missing stable UI panel, child-step status reporting still noisy |
| W1 Import | Novel/file import into proposals and project structure | Verified and actively used | Import modal and polling flow present | `active` | `FRONTEND_BACKEND_CHECKLIST.md` | Quality still being tuned for chunking/entity completeness |
| W2 Manuscript Sync | Sync writing content back into canonical/project data proposals | Verified in backend | Writing Chapters trigger with status/result path to Workbench Inbox | `active` | `FRONTEND_BACKEND_CHECKLIST.md` | Proposal acceptance safety remains owned by Workbench |
| W3 Writing Assistant | Continue/rewrite/expand/improve-dialogue flows | Verified and wired | Available in writing flows | `active` | `FRONTEND_BACKEND_CHECKLIST.md` | Occasional preamble text still needs prompt hardening |
| W4 Consistency Check | Detect contradictions and consistency issues | Verified and wired | Audit button and polling present | `active` | `FRONTEND_BACKEND_CHECKLIST.md` | Issue review/queue-fix closure still lighter than target product loop |
| W5 Simulation | Scenario/reviewer-style simulation engines | Verified and wired | Triggered from Simulation workspace | `active` | `FRONTEND_BACKEND_CHECKLIST.md` | Engine UX still scaffold-level in places |
| W6 Beta Reader | Persona-based reading feedback | Verified and wired | Triggered from Beta Reader workspace | `active` | `FRONTEND_BACKEND_CHECKLIST.md` | Persona authoring and comparative review need more product closure |
| W7 Metadata Ingestion | Reference library ingestion and style grounding | Verified and wired | Metadata workspace supports import and status | `active` | `FRONTEND_BACKEND_CHECKLIST.md` | Style extraction quality still uneven for some genres |

## Current Product Gaps That Are Real
- W0 backend exists, but there is no canonical production UI for goal composition, permissions, and step control.
- W2 now has a canonical Writing Chapters trigger and status/result path; proposal acceptance safety remains a Workbench closure item.
- Proposal acceptance and canonical-data safety still need a stronger end-to-end user path across Workbench, Writing, and shared references.
- Publish/export remains present as a workspace but is not yet a fully closed delivery surface.
- Sidecar lifecycle, lock handling, and restart ergonomics still need runtime hardening.

## Workflow Ownership Boundaries
- Status changes update this file.
- Bridge/action wiring changes update `FRONTEND_BACKEND_CHECKLIST.md`.
- Deep workflow implementation details remain in code and `langgraph.md`, which is reference-only.
