# Data Model

## Project Storage Model
Narrative IDE stores each project as a folder.

```text
<ProjectName>/
  project.json
  entities/
    characters/
      char_<id>.json
    timeline/
      event_<id>.json
      branches.json
    world/
      item_<id>.json
      containers.json
    graph/
      board_<id>.json
    relationships.json
  writing/
    chapters/
      chapter_<id>.json
    scenes/
      scene_<id>.md
      scene_<id>.meta.json
  assets/
    portraits/
    world/
    maps/
    graph/
  exports/
    markdown/
    html/
  system/
    inbox.json
    history.json
    issues.json
    index-cache.json
    runtime/
      agent_runtime.db
      langgraph_checkpoints.db
    imports/
      <lineage_id>/
        attempts/<attempt_id>/
```

## Canonical Rules
- `project.json` stores metadata and project-level indexes only.
- Long-form scene content is stored per scene file.
- Structured entities use stable IDs and split JSON files.
- Uploaded assets are copied into the project folder.
- UI components must access project data through repositories and services, not direct file reads.

## Entity Summary
### Character
- id
- name
- summary
- background
- aliases
- birthdayText
- portraitAssetId
- traits
- goals
- fears
- secrets
- speechStyle
- arc
- experience[] (`id`, `chapter`, `fact`, optional `evidence`)
- customAttributes[] (`id`, `label`, `value`), ordered for flexible profile facts
- tagIds
- organizationIds
- linkedSceneIds
- linkedEventIds
- linkedWorldItemIds
- statusFlags

### Candidate
- id
- name
- background
- summary

### Timeline Event
- id
- title
- summary
- time
- branchId
- orderIndex
- locationIds
- participantCharacterIds
- linkedSceneIds
- linkedWorldItemIds
- tags

### Chapter
- id
- title
- summary
- goal
- notes
- sceneIds
- orderIndex
- status

### Scene
- id
- chapterId
- title
- summary
- content
- orderIndex
- povCharacterId
- linkedCharacterIds
- linkedEventIds
- linkedWorldItemIds
- status

### World Container
- id
- name
- type
- isDefault
- categoryPath
- parentId

`parentId` is the stable notebook/folder relationship key. World navigation is a single
`Notebook -> Folder -> Item` tree. UI hierarchy must use stable IDs rather than display names,
and each folder must appear once in the projection. `categoryPath` is a legacy migration input,
not a runtime grouping rule.

### World Item
- id
- containerId
- folderId (canonical parent folder; `containerId` remains compatibility-only)
- type
- name
- description
- attributes
- categoryPath
- parentId
- linkedCharacterIds
- linkedEventIds
- linkedSceneIds
- mapMarkers

World folders are semantic boundaries. Organizations, locations, rules, and techniques must be
routed to compatible folders. Ambiguous candidates remain quarantined for review.

### Import review and relocation
- `CandidateLedgerEntry`: candidate identity, source evidence, inferred type, confidence, and review status
- `WorldReviewDecision`: accepted type, target folder, evidence, and rationale
- `RelocationPlan`: source candidate, target entity, field merge plan, and idempotency key

Relocation is single-writer and idempotent. Character-like candidates such as `正门主王六` can
be merged into `王六` in staged review; uncertain candidates are not forced into `门派组织`.
Canonical changes still require package-scoped proposal acceptance.

### Graph Board
- id
- name
- description
- nodes
- edges

### Proposal
- id
- title
- source
- description
- targetEntityType
- targetEntityId
- preview
- status
- createdAt
- resolvedAt
- operations
- source_workflow
- importRunId / packageId (optional import package grouping)
- packageCompiler (optional compiled package contract: version, order, proposal count, complete ordered proposal IDs)
- lastBlockReason

### Durable Agent Runtime
- `AgentRun`: `workflowId`, `lineageId`, safe non-secret configuration, budget policy, status, and version metadata
- `AgentAttempt`: unique `attemptId`, parent attempt/checkpoint reference, status, and recovery/fork provenance
- `RunLease`: worker owner, fencing token, heartbeat, and expiry; stale owners cannot publish resumable state
- `RunEvent`: monotonic per-attempt sequence with auditable stage/tool/approval/artifact summary
- `ToolCallReceipt`: idempotency key, intent/result/unknown status, safe usage/cost metadata, and receipt reference
- `RuntimeCheckpoint`: checkpoint ID, parent ID, immutable metadata, and optional strict `W1SupervisorSnapshot/v1` reference
- `HumanDecision`: idempotent pause/resume/cancel/fork or exact unknown-provider retry authorization
- `W1BudgetPolicy`: server-normalized cost/call/token limits. Resume may only tighten limits.

### W1 Resume Snapshot
- `W1SupervisorSnapshot/v1`: immutable, project-relative, hash-verified snapshot reference for a stable W1 attempt
- `W1ResumeState/v1`: typed writer dependencies for characters, tags, relationships, World, timeline branches/events, chapters/scenes, and organizer output
- `W1SourceTextRef/v1`: source-derived text reference (`SourceSpan`, source hash) used instead of storing manuscript prose in snapshot state

Snapshot state must not contain raw chapter/scene bodies, prompt text, hidden reasoning, API credentials, or absolute project paths. Invalid/missing proof is preview-only and cannot be resumed/forked.

### Consistency Issue
- id
- title
- description
- severity
- status
- referenceIds
- fixSuggestion

## Graph Node Kinds
- free_note
- character_ref
- event_ref
- location_ref
- world_item_ref
- image_card
- group_frame

## Reference and Lifecycle Rules
- Cross-page links are always stored by ID.
- AI-originated changes enter Workbench as proposals.
- W1 import proposals may be grouped into a package by `importRunId`; only a complete pending package may be accepted. `w1-package-graph-v2` stores the authoritative topological order on every proposal, and validation plus application consume the same order in one transaction so same-package IDs can satisfy character/event/branch/world/relationship references.
- `waiting_human` means a proposal gate, unknown provider outcome, or explicit human action is required. It is not canonical import completion.
- A Time Travel fork is a child `AgentAttempt`, not mutation of the selected parent checkpoint or canonical project state.
- Manual structured creation in Graph writes directly to canonical project state.
- Accepted or rejected proposals move to history and stop contributing unread highlights.
- Archive is the default delete behavior.
- Hard delete is secondary and blocked when references exist.
- Consistency and future agents may suggest auto-fix actions but cannot silently rewrite canonical references.

## Unread Update Model
Unread state exists at three levels:
- activity
- sidebar section
- entity

User actions clear unread state when they review or resolve the corresponding item.
