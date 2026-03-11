# Iteration 1: Characters Workspace Refinement

- **Goal:** Align `CharactersWorkspace` with `UI_logic.txt` layout and `DEV_UI_TOKENS.md` design system.
- **Start Time:** 2026-03-06 03:00
- **Proposed Changes:**
  - Move character/candidate list logic to Workspace left column, filtered by `sidebarSection`.
  - Replace hardcoded hex colors with semantic tokens.
  - Implement basic required field validation (inline).
  - Update `Sidebar.tsx` to handle Character activity sections if needed.
- **Tests to Execute:**
  - P0-2 Activity Navigation
  - P0-4 Character Creation
  - P0-5 Candidate Confirmation
