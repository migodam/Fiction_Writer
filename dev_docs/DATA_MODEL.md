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
- lastBlockReason

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
- W1 import proposals may be grouped into a package by `importRunId`; accepting the full package uses transaction-style draft apply so same-package IDs can satisfy character/event/branch/world/relationship references.
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
