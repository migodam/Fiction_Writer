# NARRATIVE IDE — DEVELOPMENT RULES

This document defines mandatory development rules for all AI agents working on this repository.

The goal is to ensure deterministic development, stable architecture, and testable UI behavior.

These rules MUST always be followed.

---

# 1. SOURCE OF TRUTH

The following documents define system behavior.

AI MUST read them before modifying any code.

dev_docs/UI_logic.txt  
dev_docs/UX_rules.txt  
dev_docs/UI_ROUTES.txt  
dev_docs/TEST_SELECTORS.txt  
dev_docs/TEST_PLAN.md  

If conflicts occur:

Priority order:

1 UI_logic  
2 UX_rules  
3 UI_ROUTES  
4 TEST_SELECTORS  
5 TEST_PLAN

AI must NOT invent new UI behavior not defined in these files.

---

# 2. TEST-FIRST DEVELOPMENT

All development must follow this loop:

1 Read TEST_PLAN.md
2 Identify failing tests
3 Implement minimal code changes
4 Run Playwright tests
5 Fix failing tests
6 Repeat

Never implement features without corresponding tests.

P0 and P1 tests MUST pass before committing changes.

---

# 3. UI CONSISTENCY RULES

The following elements MUST remain consistent across all pages:

Layout:

Top Toolbar  
Activity Bar  
Sidebar  
Workspace  
Global Inspector  
Status Bar

The layout must NEVER change per page.

Pages only change content inside Workspace.

---

# 4. SELECTOR RULE

All interactive UI elements MUST have stable selectors.

Use:

data-testid

Example:

<button data-testid="activity-btn-characters">

Selectors MUST follow definitions in:

dev_docs/TEST_SELECTORS.txt

AI must NEVER generate selectors based on:

CSS class  
DOM hierarchy  
random attributes

Only data-testid.

---

# 5. ROUTING RULE

Routes must follow:

dev_docs/UI_ROUTES.txt

Rules:

Every route must render a valid workspace.

No blank screens.

Invalid entity IDs must show:

"Entity not found"

with navigation options.

---

# 6. STATE MANAGEMENT

Global UI state must be handled by Zustand.

Store responsibilities:

selectedEntity  
currentRoute  
sidebarSection  
workspaceView  
editorState  

State must be centralized.

Avoid local component state for global UI.

---

# 7. PERSISTENCE

Data storage strategy:

Phase 1:

JSON persistence

Phase 2:

SQLite migration

Persistence layer must be abstracted.

UI must not directly read/write storage.

Use:

services/
repositories/

---

# 8. WRITING EDITOR RULE

Writing Studio editor must:

Autosave text  
Support undo/redo  
Never block typing

Autosave must be debounced.

Save status must appear in Status Bar.

---

# 9. ERROR HANDLING

UI must never crash.

All failures must show:

Error message  
Root cause hint  
Actionable next step

AI failures must show Failure Analysis panel in Workbench.

---

# 10. SAFE REFACTORING

AI must NEVER refactor working modules unless:

Tests exist  
Tests pass before refactor  
Tests pass after refactor

If no tests exist → do not refactor.

---

# 11. DOCUMENTATION UPDATE RULE

If AI modifies:

UI layout  
Selectors  
Routes  
Core architecture

Then AI must update corresponding docs in dev_docs.

Docs must remain synchronized with implementation.

---

# 12. DEVELOPMENT LOG

Every iteration must record:

changes made  
files modified  
tests executed  
test results  

Log must be saved in:

dev_logs/

---

# END