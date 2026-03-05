# Architecture Notes

## Platform
- Windows-only demo target.
- Electron shell.
- React UI with Vite.

## Layout
- VSCode-style layout with:
  - Top Toolbar
  - Activity Bar (Left icon rail)
  - Sidebar (Contextual second-level navigation)
  - Workspace (Main panel)
  - Inspector (Right panel)
  - Status Bar (Bottom)

## Routing
- Using React Router.
- Routes follow `UI_ROUTES.txt`.

## State
- Zustand for UI state and project data.

## Selection Model
- Global selection driven by (type, id).
- Workspace click sets selection.
- Inspector listens to selection.

## Persistence
- JSON files stored locally (Phase 1).
