# NARRATIVE IDE — SYSTEM ARCHITECTURE

Target Platform:

Desktop IDE

Technology Stack:

Electron  
React  
Zustand  
Playwright  
Node.js  

The system architecture follows a layered model.

---

# 1. HIGH LEVEL ARCHITECTURE

System layers:

Electron Shell  
React UI Layer  
Application State Layer  
Service Layer  
Persistence Layer  
AI Engine  

Diagram:

Electron
   │
React UI
   │
Zustand Store
   │
Application Services
   │
Data Repositories
   │
Storage (JSON → SQLite)

---

# 2. ELECTRON LAYER

Responsibilities:

Window creation  
Application lifecycle  
File system access  
Native OS integration  

Electron must NOT contain business logic.

UI logic belongs to React.

---

# 3. REACT UI LAYER

React handles:

Layout  
Rendering  
User interaction  

UI structure:

Activity Bar  
Sidebar  
Workspace  
Global Inspector  
Status Bar

React components must be modular.

Example structure:

src/ui

activity-bar  
sidebar  
workspace  
inspector  
status-bar

---

# 4. STATE MANAGEMENT

State manager:

Zustand

Global store includes:

selectedEntity  
currentActivity  
sidebarSection  
timelineZoom  
editorState  
workspaceFilters  

Store must remain minimal and predictable.

Avoid nested complex state objects.

---

# 5. APPLICATION SERVICES

Services coordinate business logic.

Examples:

CharacterService  
TimelineService  
GraphService  
WorldModelService  
WritingService  

Services must be pure logic.

Services must not contain UI code.

---

# 6. DATA REPOSITORIES

Repositories abstract persistence.

Example:

CharacterRepository  
TimelineRepository  
WorldRepository  

Responsibilities:

load entities  
save entities  
delete entities  
query entities  

Repositories hide storage implementation.

---

# 7. PERSISTENCE LAYER

Phase 1:

JSON storage

Example structure:

project.json

characters  
timeline  
world  
graph  
writing  

Phase 2:

SQLite migration.

Schema example:

characters table  
events table  
world_items table  
graph_nodes table  

UI must not depend on storage type.

---

# 8. AI ENGINE

AI system lives outside UI layer.

Responsibilities:

prompt generation  
LLM calls  
response parsing  
project updates  

AI operations must produce structured outputs.

Example:

JSON patches  
entity updates

AI must not directly manipulate UI state.

AI updates go through Services.

---

# 9. TESTING ARCHITECTURE

Testing framework:

Playwright

Tests must validate:

navigation  
CRUD operations  
timeline interaction  
graph interaction  
writing editor  
cross-page navigation  

Selectors must follow:

TEST_SELECTORS.txt

---

# 10. DEVELOPMENT LOOP

Development follows an automated loop:

1 AI reads dev_docs
2 AI runs Playwright tests
3 AI identifies failures
4 AI implements minimal fixes
5 AI reruns tests
6 Repeat

Goal:

Stable UI with deterministic behavior.

---

# END