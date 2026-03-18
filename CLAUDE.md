# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
npm install              # Install dependencies (Node.js v20+ required)
npm run electron:dev     # Start full app (Vite dev server + Electron)
npm run ui:dev           # Start web-only dev server (port 3000)
npm run ui:build         # TypeScript check + production build
npm run ui:lint          # ESLint
npm run ui:format        # Prettier
npm run test:e2e         # Run Playwright E2E tests
```

## Architecture

**Local-first desktop app**: Electron shell wrapping a React SPA. Privacy-first — avoid external API calls unless the user explicitly requests them; prefer local LLM interfaces (Ollama, llama-cpp).

### Layer separation

```
Electron (src/electron/main.js)
  └─ Window creation, IPC handlers (file dialogs, app settings, AI provider test)

React SPA (src/ui-react/)
  └─ App.tsx: root layout — TopToolbar / ActivityBar / Sidebar / Workspace / AgentDock / StatusBar

State: Zustand (src/ui-react/store.ts)
  ├─ UIStore  — layout, panel widths, modals, locale, density, selected activity
  └─ ProjectStore — entities (characters, scenes, chapters, timeline events, world items, etc.)

Services (src/ui-react/services/)
  ├─ projectService.ts  — entity CRUD, JSON file I/O (Phase 1; SQLite planned for Phase 2)
  ├─ electronApi.ts     — IPC bridge to Electron
  └─ appSettingsService.ts — user preferences persisted via Electron IPC

Models: src/ui-react/models/project.ts (TypeScript types, schema v4)
Routes: src/ui-react/config/routes.tsx (11 workspace modules)
```

### Global selection model

`setSelectedEntity(type, id)` is the single store action that drives the Inspector panel, highlights in lists/graphs, modal openings, and status bar display. Any cross-view navigation goes through this.

### Routing

11 route-based workspace modules: `workbench`, `writing`, `characters`, `timeline`, `graph`, `world`, `simulation`, `beta-reader`, `consistency`, `agents`, `publish`, `insights`. Routes are config-driven in `config/routes.tsx` with `sidebarSections` and `sidebarActions` per module.

### i18n

`src/ui-react/i18n.ts` — English and Chinese translations. All user-facing strings must use translation keys.

## Mandatory Development Rules

These rules from `dev_docs/DEV_RULES.md` MUST be followed:

1. **Read specs first**: Before modifying any code, read the relevant files in `dev_docs/` — priority order: `UI_logic.txt` > `UX_rules.txt` > `UI_ROUTES.txt` > `TEST_SELECTORS.txt` > `TEST_PLAN.md`. Do not invent UI behavior not defined there.

2. **Test-first loop**: Read `TEST_PLAN.md` → identify failing tests → implement minimal changes → run `npm run test:e2e` → fix failures. P0 and P1 tests must pass before committing.

3. **Layout is immutable**: The shell layout (TopToolbar, ActivityBar, Sidebar, Workspace, GlobalInspector, StatusBar) must never change between pages. Only Workspace content changes per route.

4. **Stable selectors only**: All interactive elements must have `data-testid` attributes matching definitions in `dev_docs/TEST_SELECTORS.txt`. Never use CSS class, DOM hierarchy, or random attributes as selectors.

5. **State in Zustand**: Global UI state (`selectedEntity`, `currentRoute`, `sidebarSection`, `workspaceView`, `editorState`) must live in the Zustand store, not local component state.

6. **No direct storage access from UI**: Components must go through `services/` for all persistence. The storage layer is abstracted for the Phase 1→2 migration.

7. **Safe refactoring**: Never refactor a working module unless tests exist and pass both before and after.

8. **Update docs**: If you modify UI layout, selectors, routes, or core architecture, update the corresponding file(s) in `dev_docs/`.

9. **Development logs**: Record changes made, files modified, tests executed, and results in `dev_logs/`.

## Git Commit Style

Use conventional commit prefixes: `feat:`, `fix:`, `docs:`, `chore:`.
