# Product Spec

## Product Definition
Narrative IDE is a Windows-first, local-first desktop application for planning, drafting, structuring, and exporting narrative projects. It combines structured project data, freeform graph sketching, proposal review, and future agent-assisted workflows in one project-folder based environment.

## Core Principles
- Project-folder first: users create and open a folder-backed project, similar to Premiere-style project initialization.
- Local-first persistence: canonical project data lives on disk in split JSON and content files.
- Shared data model: Characters, Timeline, Writing, World, Graph, Workbench, and export all operate on the same canonical IDs and references.
- Proposal gatekeeping: AI-generated changes never mutate canonical data directly. They must enter Workbench and be accepted or rejected by the user.
- Mixed graph model: Graph boards can contain both freeform notes and structured entity references long term.
- Reference safety: referenced entities cannot be hard-deleted without an explicit impact review.
- Agent-ready shell: the UI must reserve space and state for future CLI-driven agents without forcing a chat-centric workflow.

## Core Workflows
1. Create or open a project folder.
2. Build core story assets in Characters, Timeline, Writing, and World.
3. Sketch freely in Graph using notes, reference cards, frames, and images.
4. Generate sync proposals from Graph, Consistency, or future agents.
5. Review all proposals in Workbench Inbox.
6. Accept or reject proposals, with accepted items becoming canonical and resolved items moving to History.
7. Export narrative content to Markdown or HTML with optional appendices.

## Shell Layout
- Top Toolbar: project lifecycle, save, command palette, future automation triggers.
- Activity Bar: module switching.
- Sidebar: section switching inside the current module.
- Workspace: main content region.
- Inspector: focused entity/proposal/issue details.
- Agent Dock: right-side global future-agent surface.
- Status Bar: project path, save state, selection, proposal counts.

## Module Responsibilities
- Workbench: proposal inbox, history, issues, bulk actions.
- Writing Studio: chapter/scene authoring with shared references and autosave.
- Characters: profile records, portrait slots, birthday text, status flags, organization links, linked scenes/events.
- Timeline: event order, branches, participant links, location links, scene links.
- Graph: mixed freeform and structured board editing, sync proposal generation.
- World Model: locations, organizations, items, lore, world map, notes, and custom containers.
- Simulation: interactive scenario runner scaffold backed by project data.
- Consistency: broken refs, state conflicts, ordering conflicts, missing links, duplicate detection.
- Beta Reader: interactive feedback simulations tied to project content.
- Publish: export configuration and Markdown/HTML export.
- Insights: project analytics and coverage dashboards.

## Deferred Features
These are intentionally deferred from the current implementation program:
- Real agent execution
- Floating agent window
- Full undo/redo history
- Version control UI
- SQLite migration
- Image generation beyond placeholder controls

## Legacy Docs Status
Older UI and route docs remain as migration references. The files in this new source-of-truth set override them when conflicts exist.
