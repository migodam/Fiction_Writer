# W4 Global Undo / Redo — Implementation Report

**Date:** 2026-06-04  
**Branch:** codex/w1-orchestrated-import-quality  
**Worker:** W4

---

## Problem

The app had no undo system. Once a character was edited and saved, a timeline event moved, or a world item updated, there was no way to reverse the action short of manually re-editing. Users have no safety net for accidental edits.

**Acceptance criteria:**
- Edit a character field → Cmd+Z → old value restored
- Drag a timeline event → Cmd+Z → event returns to original branch
- Selection changes (setSelectedEntity) must NOT add undo stack entries
- UI shows undo/redo availability via toolbar button state

---

## Architecture

**Snapshot-based undo in the Zustand project store.**

Before each undoable mutation, `captureUndoSnapshot(label)` captures the entire persisted project data slice into an `UndoEntry`. `undoAction()` restores the before-snapshot and calls `saveProject()` to persist to disk. `redoAction()` re-applies the reverted state. Both undo and redo operations flush to disk.

### Core types

```typescript
const MAX_UNDO_DEPTH = 20;

type ProjectDataSnapshot = Pick<ProjectState,
  | 'characters' | 'characterTags' | 'characterPartitions' | 'candidates'
  | 'timelineEvents' | 'timelineBranches' | 'relationships'
  | 'chapters' | 'scenes' | 'currentSceneContent'
  | 'worldContainers' | 'worldItems' | 'worldSettings' | 'worldMaps'
  | 'graphBoards' | 'activeGraphBoardId'
  | 'betaPersonas' | 'betaRuns'
  | 'simulationEngines' | 'simulationLabs' | 'simulationReviewers' | 'simulationRuns'
  | 'proposals' | 'proposalHistory' | 'issues' | 'exports' | 'archivedIds'
  | 'todos' | 'manuscriptNodes'
  | 'importJobs' | 'promptTemplates' | 'ragDocuments' | 'ragChunks'
  | 'scripts' | 'storyboards' | 'videoPackages' | 'taskRequests' | 'taskRuns'
  | 'taskArtifacts' | 'taskRunLogs'
>;

interface UndoEntry {
  id: string;
  label: string;
  snapshot: ProjectDataSnapshot;
}
```

**Explicitly excluded from snapshots:** `undoStack`, `redoStack`, `saveStatus`, `selectedEntity`, `projectName`, `projectRoot`, `currentProject`, all W1–W7 workflow state, orchestrator state, UI metadata, filter/selection state.

---

## Files Changed

| File | Change |
|---|---|
| `src/ui-react/store.ts` | Types, `extractSnapshot`, `captureUndoSnapshot`, `undoAction`, `redoAction`, ~40 wrapped mutations |
| `src/ui-react/App.tsx` | Cmd+Z keyboard shortcut, toolbar undo/redo buttons wired with disabled state |
| `tests/e2e/p1/global_undo.spec.ts` | 4 new Playwright acceptance tests |

---

## Mutations Coverage

### Wrapped (captureUndoSnapshot called)

**Characters (14):** `addCharacter`, `updateCharacter`, `deleteCharacter`, `addRelationship`, `updateRelationship`, `deleteRelationship`, `addCharacterTag`, `updateCharacterTag`, `deleteCharacterTag`, `toggleCharacterTagMembership`, `addCharacterPartition`, `deleteCharacterPartition`, `confirmCandidate`, `rejectCandidate`

**Timeline (10):** `addTimelineEvent`, `updateTimelineEvent`, `deleteTimelineEvent`, `addTimelineBranch`, `updateTimelineBranch`, `deleteTimelineBranch`, `createTimelineBranch`, `moveTimelineEvent`, `setTimelineBranchGeometry`, `setTimelineBranchAnchors`

**Writing (6):** `addChapter`, `updateChapter`, `deleteChapter`, `addScene`, `updateScene`, `deleteScene`

**Manuscript (4):** `addManuscriptNode`, `updateManuscriptNode`, `deleteManuscriptNode`, `moveManuscriptNode`

**World (7):** `addWorldContainer`, `updateWorldContainer`, `deleteWorldContainer`, `addWorldItem`, `updateWorldItem`, `deleteWorldItem`, `updateWorldSettings`

**Graph (9):** `addGraphBoard`, `updateGraphBoard`, `deleteGraphBoard`, `addGraphNode`, `updateGraphNode`, `deleteGraphNode`, `addGraphEdge`, `deleteGraphEdge`, `updateGraphEdge`

**Proposals (3):** `resolveProposal`, `resolveProposals`, `resolveAllProposals`

**Total wrapped: 53 mutations**

### Explicitly NOT wrapped

| Mutation | Reason |
|---|---|
| `updateTimelineEventPosition` | Fires many times per second during drag rendering; intermediate positions not worth undoing |
| `setSelectedEntity`, `clearUnreadEntity`, `clearUnreadActivity` | UI state, not project data |
| `setActiveGraphBoard`, `syncProjectUiState` | UI state |
| `loadProject`, `openProject`, `createProject` | Clear stacks instead |
| All W0–W7 workflow mutations | Workflow state is excluded from snapshot type |

---

## Test Results

```
tests/e2e/p1/global_undo.spec.ts  4 passed (3.1s)

  ✓ updateCharacter pushes to undo stack and undoAction restores previous state
  ✓ moveTimelineEvent pushes to undo stack and undoAction restores event branch
  ✓ setSelectedEntity does not create undo stack entries
  ✓ redoAction re-applies change after undoAction
```

P0 regression: 18 failures confirmed pre-existing on the commit prior to this work (identical failure set). No regressions introduced.

---

## Known Limitations

1. **`updateTimelineEventPosition` not wrapped** — fires during drag rendering (many times/sec). The drag-completing action `moveTimelineEvent` IS wrapped, so the final committed position is undoable.

2. **Disk persistence requires `saveProject()`** — `undoAction`/`redoAction` call `saveProject()` to flush the restored state. This means undo takes a round-trip through the persistence layer. On very large projects this may feel slightly slow (~100ms).

3. **Stack is runtime-only** — the `undoStack`/`redoStack` are not persisted to disk. Reloading the project clears the undo history.

4. **Text field exclusion is conservative** — the keyboard handler checks `instanceof HTMLInputElement`, `instanceof HTMLTextAreaElement`, and `isContentEditable`. ProseMirror/TipTap editors using `role="textbox"` without `contentEditable` are not excluded here, but in practice TipTap does set `contentEditable="true"` on the editor div, so Cmd+Z will be passed through to the native text undo correctly.

---

## Manual Smoke

1. Open app with an existing project.
2. Navigate to Characters, edit a character name in the inspector, click Save.
3. Press Cmd+Z — the name reverts to the previous value.
4. Press Cmd+Shift+Z — the name re-applies.
5. Navigate to Timeline, drag an event from one branch to another.
6. Press Cmd+Z — the event returns to its original branch.
7. Toolbar Undo button should be greyed out when stack is empty; enabled after a mutation.
