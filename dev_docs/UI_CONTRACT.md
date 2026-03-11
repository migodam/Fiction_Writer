# UI Contract (v0.1)

This document defines the expected UI layout, panels, buttons, and routing transitions for each major activity in the Narrative IDE.

## Global Layout Elements
*   **AppShell**: Container for all views.
*   **TopToolbar**: Always visible.
    *   *Buttons*: New Project, Open Project, Save Project, Run AI, Run Simulation, Check Consistency, Export Book.
    *   *Search*: Global search input (`Ctrl+P`).
*   **ActivityBar**: Always visible (Left). Switches main workspace route and sidebar configuration.
*   **StatusBar**: Always visible (Bottom). Shows project name, save status, active selection label.
*   **Inspector (Right Panel)**: Shared context panel.
    *   *Tabs*: Details, Links, History.
    *   *Buttons*: Save, Delete (if applicable).

## Activity Pages

### 1. Workbench (`/workbench`)
*   **Sidebar**: Agent Console, Prompt Library, AI History, System Logs.
*   **Workspace**: Chat/Console interface.
    *   *Buttons*: Run Prompt, Retry Last, Clear Console.

### 2. Writing Studio (`/writing`)
*   **Sidebar**: Chapters, Scenes, POV Characters, Story Beats.
*   **Workspace**: Text editor.
    *   *Buttons*: Generate Scene, Rewrite, Continue, Improve Dialogue.
    *   *Context Panel (Right)*: Insert Event, Insert Character, Insert Lore.
*   **Interactions**: Autosaves content; Undo/Redo scoped to text only.

### 3. Characters (`/characters`)
*   **Sidebar**: Character List, Candidate Queue, Relationships, Tags.
*   **Workspace**: 
    *   *Left*: List panel.
    *   *Center*: Profile panel (Name, Aliases, Background, Traits, etc.).
    *   *Buttons*: New Character, Generate Candidates, Generate Backstory, Generate Traits, Open Timeline, Open Relationships.
*   **Interactions**: Candidates have Confirm/Reject buttons.

### 4. Timeline (`/timeline`)
*   **Sidebar**: Events, Locations, Chapters, Branches.
*   **Workspace**: Timeline canvas.
    *   *Toolbar*: Add Event, Add Branch, Filter, Zoom, View mode (Linear/Chapter/Character/Location).
    *   *Node interactions*: Click (selects), Drag (reorder/move branch), Right-click (context menu).

### 5. Graph (`/graph`)
*   **Sidebar**: Narrative Graph, Relationship Graph, Causality Graph, Location Graph.
*   **Workspace**: Interactive network graph.
    *   *Toolbar*: Add Node, Add Edge, Auto Layout, Reset Layout, Run Analysis.
    *   *Node interactions*: Click (selects), Drag (moves, persists).

### 6. World Model (`/world`)
*   **Sidebar**: Containers (Notebooks, Maps, Organizations, Lore, + Custom).
*   **Workspace**: 
    *   *Left*: Container list.
    *   *Center*: Items list.
    *   *Right*: Editor panel (Name, Description, Dynamic KV fields).
    *   *Buttons*: Create Container, Add Item, Import, Generate Detail.

### 7. Simulation (`/simulation`)
*   **Sidebar**: Runs, Scenarios, Comparisons, Reports.
*   **Workspace**: Run list / output tables.
    *   *Buttons*: Run, Create Scenario, Compare, Export Report.

### 8. Beta Reader (`/beta-reader`)
*   **Sidebar**: Placeholder.
*   **Workspace**: Placeholder.

### 9. Consistency (`/consistency`)
*   **Sidebar**: Categories, Issues, Ignored.
*   **Workspace**: Issues list.
    *   *Buttons*: Run Check, Auto Fix, Ignore, Open in Workbench.

### 10. Publish (`/publish`)
*   **Sidebar**: Formats, Metadata, Preview, Assets.
*   **Workspace**: Export settings.
    *   *Buttons*: Generate Blurb, Generate Cover, Export, Package.

### 11. Insights (`/insights`)
*   **Sidebar**: Project Stats, Character Stats, Pacing, Narrative Insights.
*   **Workspace**: Charts/Metrics.
    *   *Buttons*: Generate Report, Compare Chapters, Analyze Arc.

## Routing Transitions
*   **Timeline -> Writing Studio**: "Open Scene" navigates to `/writing` and focuses the correct scene.
*   **Timeline -> Graph**: "Highlight in Graph" navigates to `/graph` and selects the node.
*   **Character -> Timeline**: "Open Timeline" navigates to `/timeline` filtered by the character.
*   **Consistency -> Workbench**: "Send To Workbench" opens `/workbench` with issue context.
