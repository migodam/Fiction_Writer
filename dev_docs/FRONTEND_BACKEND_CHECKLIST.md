# Frontend ↔ Backend ↔ AI Checklist

> Integration source of truth for UI action -> store -> Electron bridge -> sidecar/workflow mapping.
> Update this file whenever a bridge, trigger, store action, endpoint, or verification state changes.
> Last updated: 2026-07-25
>
> **Status legend:**
> - ✅ COMPLETE — full chain verified end-to-end
> - ⚠️ STUB — chain exists but workflow is mock/placeholder
> - ❌ GAP — one or more chain layers missing
> - 🔵 FRONTEND_ONLY — no backend needed
> - 🧪 UNTESTED — chain wired but not yet runtime-verified

---

## How to maintain this file

When adding a new button or feature:
1. Add a new row to the relevant page section
2. Fill in all chain layers you have implemented
3. Mark status as 🧪 UNTESTED
4. After verifying end-to-end, update to ✅ COMPLETE

## Verification Boundary (2026-07-15)

Older rows retain historical implementation notes. They are not proof that a
live DeepSeek/provider call or real import-fixture acceptance passed in this
worktree. The resilience work has automated Python and mocked-IPC/Playwright
coverage only; exact commands and outcomes are in
`dev_logs/2026-07-15-agent-runtime-resilience.md`.

---

## Pages and Features

### Writing Studio

| UI Element | Component File | Store Action | electronApi Method | IPC Channel | Sidecar Endpoint | AI Workflow | Status | Notes |
|---|---|---|---|---|---|---|---|---|
| Continue writing button | WritingWorkspace.tsx | startW3 | w3Start | w3:start | POST /workflow/w3/start | W3 Writing Assistant (DeepSeek) | ✅ COMPLETE | Phase 6: DeepSeek; endpoint routing fixed 2026-04-06 |
| Select option (3-option mode) | WritingWorkspace.tsx | selectW3Option | w3Select | w3:select | POST /workflow/w3/select | W3 (resume) | ✅ COMPLETE | Phase 7: three_options + select verified (D5) |
| W3 status poll | WritingWorkspace.tsx | — | w3Status | w3:status | GET /workflow/w3/status | — | 🔵 FRONTEND_ONLY | |
| W2 sync selected chapter | WritingWorkspace.tsx | startManuscriptSync | w2Start + w2Status | w2:start + w2:status | POST /workflow/w2/start + GET /workflow/w2/status | W2 Manuscript Sync (DeepSeek) | ✅ COMPLETE | Writing Chapters trigger polls status, reports proposal count, and links to Workbench Inbox |

### Characters

| UI Element | Component File | Store Action | electronApi Method | IPC Channel | Sidecar Endpoint | AI Workflow | Status | Notes |
|---|---|---|---|---|---|---|---|---|
| Accept candidate | CharactersWorkspace.tsx | acceptCandidate | — | — | — | — | 🔵 FRONTEND_ONLY | local store only |
| Reject candidate | CharactersWorkspace.tsx | rejectCandidate | — | — | — | — | 🔵 FRONTEND_ONLY | |
| Generate portrait | CharactersWorkspace.tsx | — | aiGenerateImage | ai:generate-image | Electron built-in | Provider image API | 🧪 UNTESTED | |
| Save portrait | CharactersWorkspace.tsx | — | portraitSave | portrait:save | — (file write) | — | 🔵 FRONTEND_ONLY | |
| Upload portrait | CharactersWorkspace.tsx | — | portraitUpload | portrait:upload | — (file copy) | — | 🔵 FRONTEND_ONLY | |
| Add relationship | CharactersWorkspace.tsx | addRelationship | — | — | — | — | 🔵 FRONTEND_ONLY | |
| Delete relationship | CharactersWorkspace.tsx | deleteRelationship | — | — | — | — | 🔵 FRONTEND_ONLY | |

### Timeline

| UI Element | Component File | Store Action | electronApi Method | IPC Channel | Sidecar Endpoint | AI Workflow | Status | Notes |
|---|---|---|---|---|---|---|---|---|
| Create event | TimelineWorkspace.tsx | createTimelineEvent | — | — | — | — | 🔵 FRONTEND_ONLY | |
| Edit event | TimelineWorkspace.tsx | updateTimelineEvent | — | — | — | — | 🔵 FRONTEND_ONLY | |
| Focus concrete linked event | TimelineWorkspace.tsx + TimelineCanvas.tsx | setSelectedEntity | — | — | — | — | ✅ COMPLETE | `?event=<id>` selects its branch, shows title/time/branch, centers once, highlights the node, and does not reclaim manual pan; verified by Playwright and actual browser. |

### Graph

| UI Element | Component File | Store Action | electronApi Method | IPC Channel | Sidecar Endpoint | AI Workflow | Status | Notes |
|---|---|---|---|---|---|---|---|---|
| Board management | GraphWorkspace.tsx | — | — | — | — | — | 🔵 FRONTEND_ONLY | |

### World

| UI Element | Component File | Store Action | electronApi Method | IPC Channel | Sidecar Endpoint | AI Workflow | Status | Notes |
|---|---|---|---|---|---|---|---|---|
| Create world entry | WorldWorkspace.tsx | addWorldEntry | — | — | — | — | 🔵 FRONTEND_ONLY | |
| Edit world entry | WorldWorkspace.tsx | updateWorldEntry | — | — | — | — | 🔵 FRONTEND_ONLY | |
| Notebook/folder ownership and move | WorldWorkspace.tsx | moveWorldItem | — | — | — | — | ✅ COMPLETE | Stable `folderId`, droppable folder IDs, one undo transaction, responsive 1280px layout. |
| Open linked event/scene/timeline | WorldWorkspace.tsx | route-backed selection | — | — | — | — | ✅ COMPLETE | Shows concrete titles and metadata, exposes broken references, and opens specific `event`/`scene` targets. |

### Consistency

| UI Element | Component File | Store Action | electronApi Method | IPC Channel | Sidecar Endpoint | AI Workflow | Status | Notes |
|---|---|---|---|---|---|---|---|---|
| Run Audit button | ConsistencyWorkspace.tsx | runConsistencyCheck | w4Start | w4:start | POST /workflow/w4/start | W4 Consistency Check (DeepSeek) | ✅ COMPLETE | Phase 6: wired to W4; was setTimeout fake; verified 2026-04-06 |
| W4 status poll | ConsistencyWorkspace.tsx | — | w4Status | w4:status | GET /workflow/w4/status | — | ✅ COMPLETE | Verified endpoint returns session state |
| Queue Fix | ConsistencyWorkspace.tsx | addProposal | — | — | — | — | 🔵 FRONTEND_ONLY | |
| Mark Resolved | ConsistencyWorkspace.tsx | resolveIssue | — | — | — | — | 🔵 FRONTEND_ONLY | |
| Hide issue | ConsistencyWorkspace.tsx | dismissIssue | — | — | — | — | 🔵 FRONTEND_ONLY | |

### Agent Console (Agents)

| UI Element | Component File | Store Action | electronApi Method | IPC Channel | Sidecar Endpoint | AI Workflow | Status | Notes |
|---|---|---|---|---|---|---|---|---|
| Send chat message | AgentChat.tsx | addTaskRequest + addTaskRun | aiChat | ai:chat | — (provider direct) | Configured AI provider | ✅ COMPLETE | Phase 6: wired to real ai:chat; was hardcoded mock; needs real API key |
| Mode switch tabs | AgentChat.tsx | setAgentChatMode (UIStore) | — | — | — | — | ✅ COMPLETE | Phase 6: persists across nav |
| Chat messages persist | AgentChat.tsx | agentChatMessages (UIStore) | — | — | — | — | ✅ COMPLETE | Phase 6: route persistence fixed |
| W0 goal/start control | W0OrchestratorPanel.tsx | startOrchestrator | orchestratorStart | orchestrator:start | POST /orchestrator/start | W0 Orchestrator (DeepSeek) | ✅ COMPLETE | Added WS-02 2026-04-24; Playwright mocked IPC coverage in `w0_orchestrator_ui.spec.ts` |
| W0 status/progress display | W0OrchestratorPanel.tsx | orchestratorStatus/progress/plan state | orchestratorStatus | orchestrator:status | GET /orchestrator/status | — | ✅ COMPLETE | Shows plan, progress, current step, completion, and errors |
| W0 permission grant | W0OrchestratorPanel.tsx | grantPermission | orchestratorGrant | orchestrator:grant | POST /orchestrator/permission/{id}/grant | — | ✅ COMPLETE | Shows permission card when status is `waiting_permission` |
| W0 permission deny | W0OrchestratorPanel.tsx | denyPermission | orchestratorDeny | orchestrator:deny | POST /orchestrator/permission/{id}/deny | — | ✅ COMPLETE | Denial moves UI to error state with reason |

### Simulation Lab

| UI Element | Component File | Store Action | electronApi Method | IPC Channel | Sidecar Endpoint | AI Workflow | Status | Notes |
|---|---|---|---|---|---|---|---|---|
| Run Lab/Reviewer button | SimulationWorkspace.tsx | runSimulation | w5Start | w5:start | POST /workflow/w5/start | W5 Simulation Engine (DeepSeek) | ✅ COMPLETE | Phase 6: wired to W5; was local stub; verified 2026-04-06 |
| Run Engine button | SimulationWorkspace.tsx | runSimulation | w5Start | w5:start | POST /workflow/w5/start | W5 (single engine) | ✅ COMPLETE | Phase 6: wired; verified |
| W5 status poll | SimulationWorkspace.tsx | — | w5Status | w5:status | GET /workflow/w5/status | — | ✅ COMPLETE | Verified endpoint returns session state |
| Create Lab/Reviewer | SimulationWorkspace.tsx | createSimulationLab / createSimulationReviewer | — | — | — | — | 🔵 FRONTEND_ONLY | |
| Add engine preset | SimulationWorkspace.tsx | addSimulationEngine + updateSimulationLab | — | — | — | — | 🔵 FRONTEND_ONLY | |

### Beta Reader

| UI Element | Component File | Store Action | electronApi Method | IPC Channel | Sidecar Endpoint | AI Workflow | Status | Notes |
|---|---|---|---|---|---|---|---|---|
| Run Persona button | BetaReaderWorkspace.tsx | runBetaReader | w6Start | w6:start | POST /workflow/w6/start | W6 Beta Reader (DeepSeek) | ✅ COMPLETE | Phase 6: wired to W6; was runBetaPersona stub; verified 2026-04-06 |
| W6 status poll | BetaReaderWorkspace.tsx | — | w6Status | w6:status | GET /workflow/w6/status | — | ✅ COMPLETE | Verified endpoint returns session state |
| Create persona | BetaReaderWorkspace.tsx | addBetaPersona | — | — | — | — | 🔵 FRONTEND_ONLY | |
| Delete persona | BetaReaderWorkspace.tsx | deleteBetaPersona | — | — | — | — | 🔵 FRONTEND_ONLY | |

### Workbench

| UI Element | Component File | Store Action | electronApi Method | IPC Channel | Sidecar Endpoint | AI Workflow | Status | Notes |
|---|---|---|---|---|---|---|---|---|
| Import novel | ImportWorkflow.tsx + WorkbenchWorkspace.tsx | startImport | w1Start | w1:start | POST /workflow/w1/start | W1 Import Compiler (DeepSeek) | ✅ COMPLETE | Hybrid compiler artifacts added; prompt_profile recorded; see W1_IMPORT_COMPILER.md |
| W1 status poll | ImportWorkflow.tsx | — | w1Status | w1:status | GET /workflow/w1/status | — | ✅ COMPLETE | Returns current_step and prompt_profile for long-import progress |
| Cancel import | ImportWorkflow.tsx | cancelImport | w1Cancel | w1:cancel | POST /workflow/w1/cancel | — | ✅ COMPLETE | Verified by `tests/e2e/p1/import_workflow.spec.ts` on 2026-04-25 final integration |
| Accept proposal package | WorkbenchWorkspace.tsx | resolveProposals | — | — | — | — | 🔵 FRONTEND_ONLY | W1 proposals, including singleton imports, remain staged and accept only as their current import package transaction. The transaction validates and consumes `stagedManuscriptProjection` into scene documents and manuscript nodes atomically. |
| Reject proposal package | WorkbenchWorkspace.tsx | resolveProposals | — | — | — | — | 🔵 FRONTEND_ONLY | Reject is scoped to the current package; no cross-run bulk action is exposed. |
| Spawn sidecar | main.js / WorkbenchWorkspace | — | sidecarSpawn | sidecar:spawn | — (process) | — | 🔵 FRONTEND_ONLY | |
| Force-clear workflow lock | WorkbenchWorkspace.tsx | — | — | workflow:force-clear | — | — | 🔵 FRONTEND_ONLY | |

### Runtime Recovery (W1)

| UI Element | Component File | Store Action | electronApi Method | IPC Channel | Sidecar Endpoint | AI Workflow | Status | Notes |
|---|---|---|---|---|---|---|---|---|
| Recoverable-run list and credentials gate | `ImportWorkflow.tsx` + `import-runtime/RecoveryCenter.tsx` | W1 runtime recovery state/actions | `runtimeRecoverable`, `runtimeResume` | `runtime:recoverable`, `runtime:resume` | `GET /runtime/runs/recoverable`; `POST /runtime/runs/{attempt_id}/resume` | W1 recovery | ✅ COMPLETE | API, mocked IPC, and real Electron project-restart discovery are covered; Import Text 18 is detected at 4/10 without exposing credentials. |
| Pause/cancel a runtime attempt | `import-runtime/RecoveryCenter.tsx` | W1 runtime action | `runtimeAction` | `runtime:pause`, `runtime:cancel` | `POST /runtime/runs/{attempt_id}/pause|cancel` | W1 recovery | ✅ COMPLETE | Commands are idempotent in API and UI tests. |
| Checkpoint timeline and immutable fork | `import-runtime/CheckpointTimeline.tsx` | W1 runtime checkpoint/fork state | `runtimeCheckpoints`, `runtimeFork` | `runtime:checkpoints`, `runtime:fork` | `GET /runtime/runs/{attempt_id}/checkpoints`; `POST /runtime/runs/{attempt_id}/fork` | W1 recovery | ✅ COMPLETE | Fork validates checkpoint ownership, creates a child attempt, and preserves the parent. |
| Durable runtime-event replay | `ImportWorkflow.tsx` + `ImportConsole.tsx` | W1 runtime event cursor | `runtimeEvents` | `runtime:events` | `GET /runtime/runs/{attempt_id}/events?afterSequence=N` | W1 recovery | ✅ COMPLETE | Monotonic sequence, deduplication, cursor replay, and gap handling are covered. |
| SSE bridge with polling fallback | `ImportWorkflow.tsx` | W1 runtime event cursor | `runtimeEventStreamSubscribe` | `runtime:event-stream-subscribe` | `GET /workflow/stream?attempt_id=...` | W1 recovery | ✅ COMPLETE | Electron Last-Event-ID replay and polling fallback are covered by `import_runtime_sse.spec.ts`; the durable runtime API remains the replay source. |

### Metadata Library

| UI Element | Component File | Store Action | electronApi Method | IPC Channel | Sidecar Endpoint | AI Workflow | Status | Notes |
|---|---|---|---|---|---|---|---|---|
| Import file (+ W7 ingest) | MetadataWorkspace.tsx | importMetadataFile + ingestMetadata | pickFiles + metadataIngest | metadata:ingest | POST /metadata/ingest | W7 Metadata Ingestion (DeepSeek) | ✅ COMPLETE | Phase 6: W7 triggered after file copy; verified 2026-04-06 |
| W7 status poll | MetadataWorkspace.tsx | — | metadataStatus | metadata:status | GET /metadata/status | — | ✅ COMPLETE | Verified via curl |
| Delete metadata file | MetadataWorkspace.tsx | deleteMetadataFile | — | — | — | — | 🔵 FRONTEND_ONLY | |

### Orchestrator (W0)

| UI Element | Component File | Store Action | electronApi Method | IPC Channel | Sidecar Endpoint | AI Workflow | Status | Notes |
|---|---|---|---|---|---|---|---|---|
| Start orchestrator | W0OrchestratorPanel.tsx | startOrchestrator | orchestratorStart | orchestrator:start | POST /orchestrator/start | W0 Orchestrator (DeepSeek) | ✅ COMPLETE | Canonical UI entry in Agents workspace; Phase 7 curl verification plus WS-02 UI coverage |
| Orchestrator status | W0OrchestratorPanel.tsx | orchestratorStatus/progress/plan/errors state | orchestratorStatus | orchestrator:status | GET /orchestrator/status | — | ✅ COMPLETE | Polling returns plan + current_step + progress + errors for UI state |
| Grant permission | W0OrchestratorPanel.tsx | grantPermission | orchestratorGrant | orchestrator:grant | POST /orchestrator/permission/{id}/grant | — | ✅ COMPLETE | Manual grant resumes polling |
| Deny permission | W0OrchestratorPanel.tsx | denyPermission | orchestratorDeny | orchestrator:deny | POST /orchestrator/permission/{id}/deny | — | ✅ COMPLETE | Deny sets status=error and surfaces reason in UI |

### App Settings

| UI Element | Component File | Store Action | electronApi Method | IPC Channel | Sidecar Endpoint | AI Workflow | Status | Notes |
|---|---|---|---|---|---|---|---|---|
| Load app settings | AdvancedSettingsModal.tsx | loadAppSettings | loadAppSettings | settings:load-app | — | — | ✅ COMPLETE | |
| Save app settings | AdvancedSettingsModal.tsx | saveAppSettings | saveAppSettings | settings:save-app | — | — | ✅ COMPLETE | |
| Test provider connection | AdvancedSettingsModal.tsx | — | testProviderConnection | settings:test-provider | Direct provider `GET /models` | — | ✅ COMPLETE | Main-process request uses Bearer auth, HTTPS/loopback validation, public-address DNS checks with the connection pinned to the validated address, 8s timeout, model-catalog validation, and typed auth/rate-limit/server/TLS/network failures. Electron smoke verifies the bridge without exposing the key. |
| Toggle locale/density/theme | AdvancedSettingsModal.tsx | setLocale/setDensity | saveAppSettings | settings:save-app | — | — | ✅ COMPLETE | |
| Create project | AdvancedSettingsModal.tsx | createProject | — | — | — | — | ✅ COMPLETE | |

### Electron Runtime Security

| Surface | Component File | Store Action | electronApi Method | IPC Channel | Sidecar Endpoint | AI Workflow | Status | Notes |
|---|---|---|---|---|---|---|---|---|
| Isolated renderer bridge | `src/electron/preload.cjs` | — | all existing named methods | named IPC allowlist | — | — | ✅ COMPLETE | `nodeIntegration: false`, `contextIsolation: true`; no renderer `ipcRenderer` escape hatch. |
| W1 project-root status route | `electronApi.ts` | W1 polling | `w1Status` | `w1:status` | GET `/workflow/w1/status` | W1 Import Compiler | ✅ COMPLETE | Electron runtime smoke verifies that the validated project root reaches the W1 route contract. |
| Runtime smoke coverage | `tests/electron/runtime_smoke.mjs` | — | file/settings/W1 bridge | loopback-only test fixture | — | — | ✅ COMPLETE | Runs with `npm run electron:smoke`; native OS dialog interaction is deterministic in smoke mode, so a headed/manual OS-dialog pass remains outside headless automation. |

---

## Gap Summary

### 2026-07-25 verification notes
- World UI uses stable Notebook/Folder/Item ownership through `folderId`; legacy `categoryPath`
  is not used for runtime placement.
- The semantic reviewer/organizer contract supports candidate ledger, relocation plans, and
  package-scoped proposal acceptance. Accepted-project offline audit is 0 errors/0 warnings;
  see the reconcile and audit tools for receipts and evidence.
- The Agent Dock has a normalized durable execution projection for plan, agent, tool call/result,
  review, approval, artifact, checkpoint, error, and result states.
- Concrete timeline deep-link behavior is committed and verified. Electron runtime smoke passed;
  a full user-project headed replay and a new real package-acceptance UI pass were not rerun.

### ❌ GAP items (missing chain layers)

_No missing implementation layer is claimed for the existing Phase 7 baseline; the remaining
wave-specific checks are listed below._

### ⚠️ STUB items (chain exists but workflow is placeholder or not triggered from UI)

_(none currently tracked in this file)_

### 🧪 UNTESTED items (need runtime verification)

- Full Agent execution replay in a user-project headed Electron session (deterministic runtime smoke passed).
- Real Workbench package acceptance with reviewer quarantine and relocation visible.

### Historical Phase 7 Record (2026-04-06)

The following is historical project documentation, not current evidence of
live-provider execution or real-fixture acceptance:

- **W1 Import** (B): 4 chunks, 77 proposals, 韩立 + alias 二愣子 correctly extracted — **8/10**
- **W2 Manuscript Sync** (C1-C3): all 3 modes pass; entity diff + proposals generated — **9/10**
- **W3 Writing Assistant** (D1-D5): continue/rewrite/expand/improve_dialogue/three_options all pass — **8/10**
- **W4 Consistency Check** (E1-E3): scene/full/contradiction-injection all pass; internal self-contradictions detected — **9/10**
- **W5 Simulation Engine** (G1-G3): 3/5/all engines all pass; 3-branch scenarios generated — **8/10**
- **W6 Beta Reader** (H1-H3): casual/scholar/shipper personas produce differentiated reports — **8/10**
- **W7 Metadata Ingestion** (F1-F2): ChromaDB updated; style-guided W3 output verified — **8/10**
- **W0 Orchestrator** (I1-I3): single/chained/complex goals all planned and executed — **8/10**
- **AgentChat Task Running**: `updateTaskRun` fix — status transitions to completed/failed after AI response

### Remaining Non-Blocking Issues

1. W3 occasional preamble headers ("续写内容：") in direct_output mode. Prompt improvement needed.
2. W7 `pov_style` returns "unknown" for xianxia. Needs Chinese-literature pov vocabulary in prompt.
