# Product Spec

## Product Definition
Narrative IDE is a local-first desktop environment for building and operating narrative projects. It combines structured project data, route-backed authoring modules, proposal review, workflow-driven analysis, and export surfaces inside one project-folder-based application.

## Active Product Boundary
- Active implementation baseline: `src/ui-react` + `src/electron` + `sidecar`
- Active shell: Top Toolbar, Activity Bar, Sidebar, Workspace, Inspector, Agent Dock, Status Bar
- Active workflow family: W0-W7, with uneven UI closure across workflows
- Reference-only legacy paths: `src/ui` and prototype-era planning docs

## Product Principles
- Project-folder first: users create/open a folder-backed project.
- Local-first persistence: canonical project data stays on disk.
- Shared data model: route modules operate on shared canonical IDs and references.
- Proposal gatekeeping: AI-originated writes enter a review flow before becoming canonical.
- Reference safety: destructive operations must respect cross-entity references.
- Headless-capable workflows: sidecar workflows should remain callable outside the Electron UI.
- Agent-ready, not chat-only: the product supports workflow orchestration without collapsing into a pure chat surface.

## Active User Journey
1. Create or open a project.
2. Build or import story structure.
3. Review workflow-generated proposals and issues in Workbench.
4. Author and revise scenes, characters, timeline, graph, and world state against shared references.
5. Run workflow-assisted checks, simulation, beta feedback, or metadata grounding.
6. Export deliverable content.

## Active Module Inventory
- Workbench: inbox, history, issues, imports/runs/prompts/task surfaces
- Writing Studio: scenes, chapters, manuscript, scripts, storyboards
- Characters: roster, candidates, relationship graph, tags
- Timeline: branch/event canvas and editing flows
- Graph: board-based freeform and structured relationship surfaces
- World Model: entries, maps, settings
- Simulation: labs and reviewers
- Beta Reader: persona-driven feedback
- Consistency: issue/audit surface
- Agents: agent/orchestrator-facing workspace
- Publish: export surfaces
- Insights: dashboards and analytics
- Reference Library: metadata/reference ingestion and chunk preview

## Current Product Gaps
- W0 Orchestrator is backend-capable but lacks a canonical production UI.
- W2 Manuscript Sync is backend-capable but lacks a canonical production trigger.
- Workbench proposal acceptance and canonical-data safety need stronger end-to-end closure.
- Publish/export remains a partial product surface.
- Sidecar lifecycle and runtime ergonomics still need hardening.

## Deferred or Not in This Wave
- New speculative workflows beyond W0-W7
- Multimodal/video expansion beyond existing placeholder surfaces
- Full undo/redo history
- Version control UI
- Large schema redesigns without dedicated planning and decision-log entries

## Document Status
This document is the product boundary source of truth. Older route/UI snapshots remain reference-only unless promoted through `dev_docs/README.md`.
