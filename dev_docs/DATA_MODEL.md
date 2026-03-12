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

### World Item
- id
- containerId
- type
- name
- description
- attributes
- linkedCharacterIds
- linkedEventIds
- linkedSceneIds
- mapMarkers

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
