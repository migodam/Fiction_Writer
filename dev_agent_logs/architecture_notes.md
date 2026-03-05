# Frontend Architecture Notes

## Current State (Phase 2)
- **Tech Stack**: Electron, React 18, Vite, TypeScript, Tailwind CSS, Zustand, Playwright.
- **Layout**: Complete Phase 1 Shell.
- **State Management**: Zustand stores handling UI, Project data, and Selection.
- **Persistence**: Scaffolding for JSON persistence.

## Project JSON Schema (Phase 1 Persistence)
```json
{
  "metadata": {
    "name": "Project Name",
    "lastModified": "2026-03-05T..."
  },
  "characters": [
    { "id": "char_1", "name": "...", "background": "...", "aliases": "..." }
  ],
  "timeline": {
    "branches": [{ "id": "branch_main", "name": "Main" }],
    "events": [
      { "id": "event_1", "title": "...", "summary": "...", "branchId": "branch_main", "orderIndex": 0 }
    ]
  },
  "writing": {
    "scenes": [
      { "id": "scene_1", "title": "...", "content": "..." }
    ]
  }
}
```

## Selection Model
The `selectedEntity` in `useProjectStore` is the source of truth for the `Inspector`.
Components must call `setSelectedEntity(type, id)` to update the global view.

## Gaps vs. Phase 2 Exit Criteria
- Electron IPC wiring for file system access (loading/saving real files).
- Global search UI component in Top Toolbar.
- "Project Open" dialog implementation.
