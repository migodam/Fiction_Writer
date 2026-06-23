# Narrative IDE Task Completion Audit

Date: 2026-06-06  
Author: Codex  
Scope: one-by-one audit of the user's requested deliverables and what was incomplete before this pass.

## Executive Verdict

The Multi-Agent Claude plan exists and covers the seven product defect areas, but the communication-folder merge was incomplete before this pass. It had an index and current-state rollup, not a true merged evidence rollup.

This pass completes the missing documentation merge by adding:

- `2026-06-06-communication-merged-evidence-rollup.md`
- this task completion audit
- README updates that mark current, merged, superseded, and retained docs
- a dev log for the correction

This pass does not implement product code. The product fixes are intentionally delegated to the Claude multi-agent workflow in `2026-06-06-w1-next-wave-multiagent-claude-plan.md`.

## Checklist

| # | User request | Status after this pass | Evidence / next action |
|---|---|---|---|
| 0 | Merge and organize `communication/` docs | Complete for first pass | `README.md` plus `2026-06-06-current-state-rollup.md` plus `2026-06-06-communication-merged-evidence-rollup.md`. No deletion/move yet. |
| 1 | Chapter split: do not make LLM output full chapters; fix truncation; distinguish Manuscript vs Chapter | Planned, not implemented | Claude W1 prompt requires source spans and deterministic body reconstruction. |
| 2 | Character module: background/experience empty, duplicates, custom attributes, right-click broken | Planned, not implemented | Claude W1 handles extraction; Claude W2 handles profile/custom attrs/dedupe/commands. |
| 3 | Relationship module: organize relationships, improve graph layout, reject false relation labels | Planned, not implemented | Claude W1 ontology, W2 relationship UI, W3 graph algorithms. |
| 4 | Character tags must be Chinese in Chinese novels | Planned; prompt strengthened in this pass | W1 backend zh guard plus W2/W4 visible UI zh acceptance. |
| 5 | Undo broken after timeline event drag | Planned, not implemented | Claude W3 transaction/command undo design. |
| 6 | World Model category/folder confusion; drag nesting broken; parser target mismatch | Planned, not implemented | Claude W3 stable notebook/folder/item model; W4 QA/docs. |
| 7 | Complete right-click operation logic with new/copy/paste/cut/drag/move etc. | Planned, not implemented | Claude W2 command registry and typed clipboard; W4 Electron/Playwright acceptance. |
| 8 | Use Multi-Agent Workflow and specify subagents/skills/research | Complete in plan | Five Claude windows W0-W4 plus required Claude skills and external references. |
| 9 | Let subagents write their own Claude prompts and merge duplicated windows | Complete in plan | Window compression from 10-11 needs into 5 Claude windows. |

## What Was Missing Before This Pass

| Missing item | Why it mattered | Correction |
|---|---|---|
| Actual communication evidence merge | README indexed files but did not merge older report content | Added `2026-06-06-communication-merged-evidence-rollup.md` |
| Explicit task-by-task completion audit | User could not see which items were done vs merely planned | Added this document |
| Stale fact in next-wave plan saying `communication/` had no README | That was true at initial observation but false after cleanup | Updated the plan to say README/rollups now exist |
| UI-visible Chinese tag acceptance was not hard enough | Backend zh checks alone do not prove the user sees Chinese labels | Strengthened W2/W4 acceptance requirements |

## Seven Defects: Current Handoff Readiness

### 1. Chapter Split / Manuscript

Ready for Claude W1.

Required algorithm:

- Treat raw source text as canonical.
- Store chapter/scene spans as offsets or stable source segment references.
- Ask the LLM for metadata only: `source_start`, `source_end`, `summary`, `beats`, `evidence`, `characters`, `world_refs`.
- Reconstruct body text deterministically from raw source.
- Split only a single oversized chapter, with explicit oversized metadata.
- Model `Chapter` as structural segmentation and `ManuscriptNode` as author-facing outline/prose projection.

Hard fail:

- Any prompt asks the LLM to emit full chapter body.
- A normal chapter is truncated.
- Manuscript and Chapter render as identical objects with no product distinction.

### 2. Character Module

Ready for Claude W1 + W2.

Required design:

- Backend extraction must populate background and experience evidence for Han Li and other major characters.
- UI must expose editable profile sections, not duplicate name/background blocks.
- Add flexible custom attributes with stable IDs or key/value entries.
- Manual dedupe/merge must preview affected relationships, events, tags, and references.
- Delete should be archive-first when references exist.
- Right-click actions must use the shared command registry.

Hard fail:

- Han Li background/experience remains empty after a supported import.
- UI duplicates the same biography text in multiple fields without dedupe rules.
- User cannot add a custom attribute.

### 3. Relationship Module

Ready for Claude W1 + W2 + W3.

Required design:

- Relationship type is a Chinese allowlist.
- Raw LLM phrases are evidence labels or notes, not canonical types.
- Relationship rows group by counterpart, direction, category, and confidence/status.
- Graph layout must be deterministic and provide auto-layout/reset.
- Edge labels use HTML/portal or equivalent collision handling, not overlapping SVG text.

Hard fail:

- `解惑`, `选拔`, or `启明者冷冰冰的师兄` becomes a relationship type.
- Dense relationship graph remains unreadable with overlapping labels.

### 4. Chinese Tags

Ready for Claude W1 + W2 + W4.

Required design:

- Internal enum values may remain English if hidden.
- User-visible tag chips, relationship types, character traits, world labels, and menu labels in zh projects must be Chinese.
- Add backend tests and Playwright-visible UI tests.

Hard fail:

- A Chinese novel import shows English default tags or labels to the user.

### 5. Undo

Ready for Claude W3.

Required algorithm:

- Use command/patch/transaction semantics for editor interactions.
- Timeline drag captures before-state on pointerdown.
- Drag movement is staged.
- Pointerup commits one transaction.
- Esc/pointercancel aborts without undo entry.
- Meta/Ctrl+Z reverts one drag only, including position and branch/order.

Hard fail:

- Timeline drag pushes multiple undo entries.
- Undo reverts unrelated import/workbench/project changes.
- Undo does nothing after event drag.

### 6. World Model

Ready for Claude W3 + W4.

Required data structure:

- Notebook/folder/item tree with stable IDs.
- Hidden root is allowed in data but not visible as a user folder.
- `categoryPath` becomes compatibility metadata, not the membership key.
- Organizer emits stable folder target IDs.
- Drag/drop supports before/inside/root moves, persistence, cycle prevention, and undo.

Hard fail:

- User still sees a top-level `category` concept.
- Timeline, character concepts, or cultivation methods are placed under the wrong module/folder because of string guessing.
- Drag handle exists but cannot drop into a valid folder target.

### 7. Right-Click Operations

Ready for Claude W2 + W4.

Required architecture:

- `CommandContext` describes selected object, surface, project, permissions, clipboard, and selection state.
- `AppCommand` describes id, label, icon, enabled/disabled reason, shortcut, execute, undo behavior, and applicable surfaces.
- Typed clipboard stores copied/cut payloads with source refs and paste constraints.
- Context menus are generated from command registry, not ad hoc arrays.

Minimum menu coverage:

| Surface | Required commands |
|---|---|
| Character card/profile | New Character, Edit/Rename, Copy, Cut, Duplicate, Merge, Archive/Delete, Add Attribute |
| Relationship row/edge | Edit Type, Add Note, Copy, Delete/Archive, Move/Group, Open Participants |
| World folder/item | New Folder, New Item, Rename, Copy, Cut, Paste, Move, Delete/Archive |
| Timeline event | Edit, Duplicate, Move to Branch, Copy, Cut, Delete/Archive |
| Blank workspace | New relevant object, Paste if valid, Select All |

Hard fail:

- Right-click opens a visual menu but commands do not execute through the same command path as keyboard/menu actions.
- Copy/cut/paste works only for text fields and not domain objects.

## Multi-Agent Workflow Status

| Requirement | Status |
|---|---|
| Use a lead model to freeze repo facts | Planned in W0 prompt |
| Use subagents for investigation before implementation | Required in all windows |
| Each worker writes Investigation Report before coding | Required |
| Each worker writes its own implementation prompt | Required |
| Merge 10-11 needs into fewer Claude windows | Done: W0-W4 |
| Require Brave Search / Context7 / Playwright / frontend-design where relevant | Required |
| Require QA screenshots/artifacts before claiming done | Required |
| Require communication docs merge worker | W4 owns docs; this pass also completed first merge rollup |

## Current Reading Order For Claude

1. `communication/README.md`
2. `communication/2026-06-06-current-state-rollup.md`
3. `communication/2026-06-06-communication-merged-evidence-rollup.md`
4. `communication/2026-06-06-task-completion-audit.md`
5. `communication/2026-06-06-w1-next-wave-multiagent-claude-plan.md`

## What Remains For Claude Implementation

The next Claude wave should not treat this audit as implementation completion. It is a corrected handoff package.

Claude must still:

- run real investigation with screenshots/artifacts;
- inspect code/storage/test paths;
- use the required skills/plugins;
- write worker reports;
- design data structures and algorithms;
- implement in controlled worktrees;
- run backend, frontend, Playwright, and Electron acceptance gates.

