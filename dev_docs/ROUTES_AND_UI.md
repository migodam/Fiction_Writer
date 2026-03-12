# Routes and UI

## Route Contract
### Workbench
- `/workbench/inbox`
- `/workbench/history`
- `/workbench/issues`
- `/workbench/bulk`

### Writing
- `/writing/chapters`
- `/writing/scenes`
- `/writing/pov`
- `/writing/beats`

### Characters
- `/characters/list`
- `/characters/candidates`
- `/characters/relationships`
- `/characters/tags`
- `/characters/profile/:characterId`

### Timeline
- `/timeline/events`
- `/timeline/locations`
- `/timeline/chapters`
- `/timeline/branches`
- `/timeline/event/:eventId`

### Graph
- `/graph/narrative`
- `/graph/relationships`
- `/graph/causality`
- `/graph/location`

### World
- `/world/notebooks`
- `/world/maps`
- `/world/organizations`
- `/world/lore`

### Simulation
- `/simulation/runs`
- `/simulation/scenarios`
- `/simulation/comparisons`
- `/simulation/reports`

### Consistency
- `/consistency/categories`
- `/consistency/issues`
- `/consistency/ignored`

### Beta Reader
- `/beta-reader/feedback`
- `/beta-reader/personas`

### Publish
- `/publish/formats`
- `/publish/metadata`
- `/publish/preview`
- `/publish/assets`

### Insights
- `/insights/project`
- `/insights/characters`
- `/insights/pacing`
- `/insights/narrative`

## Shell Rules
- No route may render a blank page.
- Invalid entity detail routes must show `Entity not found` and a recovery navigation action.
- Sidebar sections are route-backed, not purely in-memory tabs.
- The sidebar highlights the canonical section for the current route.
- Inspector is reserved for the current selection and must work for entities, proposals, and issues.

## Agent Dock Rules
- The Agent Dock lives on the right side of the shell.
- It must support expanded and collapsed states.
- It shows project context, proposal counts, issue counts, and a future task summary region.
- Future floating windows are deferred and do not block current implementation.

## Workbench Rules
- Workbench is not a chat console.
- Graph, Consistency, and future agent outputs all route into Workbench Inbox.
- History contains resolved proposals only.
- Issues contains consistency and validation problems.
- Bulk Actions is reserved for batch-safe proposal operations.

## Graph Rules
- A single board can mix freeform notes and structured reference cards.
- Graph sync actions create proposals, not direct AI mutations.
- Structured reference cards should feel visually distinct from free notes.

## Design Direction
- Visual tone: dark cinematic base with limited archival details.
- Avoid generic admin-dashboard composition.
- Use semantic design tokens instead of raw colors inside components.
