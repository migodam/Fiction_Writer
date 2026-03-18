# Narrative IDE: Project State & Strategic Roadmap

## 1. Executive Summary
The **Narrative IDE** is a Local-First AI Fiction Writing Software designed for long-term, AI-empowered fiction creation. It transitions the paradigm from "chat-based AI generation" to a "Software Engineering (SWE) structured workflow" for storytelling.

Currently, the project possesses a highly robust core data model and excellent testing infrastructure. However, to reach a commercial "on-board" state, it requires significant upgrades in **Long-Horizon Autonomy**, **Massive Scale (100+ chapters) Processing**, and **Multi-modal Pipelines (Script to Video)**.

---

## 2. Current State & Completion Metrics (SWE Perspective)

| Module | Completion | Analysis & Current State |
| :--- | :--- | :--- |
| **Core Data & Persistence** | **85-90%** | Excellent tree-based modeling (`Project` -> `Chapter` -> `Scene`). Safe, chunked JSON storage allows O(1) retrieval without loading the entire book. |
| **Testing & Robustness** | **85%** | High commercial standard. Simulation scripts (`tests/simulate_*.py`) prove the engine's resilience under complex operations. |
| **AI Orchestration (RAG)** | **60%** | Good foundation (`context_builder.py`), but currently reactive. Lacks proactive, multi-agent conflict resolution. |
| **GUI (React/Electron)** | **45-50%** | Architecture is set, but many advanced UI components (timelines, graph editors) defined in `dev_docs` are incomplete or mocked. |
| **CLI Automation** | **50%** | Supports single operations, but lacks batch-processing commands for global narrative refactoring. |
| **Structural Ingestion** | **10%** | **Critical Gap.** No pipeline exists to parse raw `.txt`/`.docx` into the structured JSON entity/chapter formats. |
| **Script/Video Modality** | **0%** | **New Requirement.** Infrastructure needs expansion to support multi-modal outputs. |

---

## 3. Core Technical Challenges & Solutions

### A. The "Hundreds of Chapters" Challenge (Massive Scale)
**Problem:** An agent cannot read 300 chapters (600k+ words) simultaneously due to LLM Context Walls.
**Solution:**
1. **Map-Reduce Summarization Pipeline:** Agents recursively summarize scenes into chapters, and chapters into arcs. Only high-level arc summaries and dynamic entity RAG are loaded into the working context.
2. **Event-Driven Consistency:** When Chapter 10 is modified, a background worker flags downstream chapters (e.g., Chapter 105) that contain dependent entities for AI review, rather than re-reading the whole book.

### B. Long-Horizon Autonomous Workflow
**Problem:** Generating or revising fiction over hours leads to Context Drift and Accumulation Errors.
**Solution:**
1. **Actor-Critic Agent Architecture:** Isolate the "Writer Agent" from the "Consistency Checker Agent." The Checker reviews every output against the global truth (Entities/World Bible) and forces rollbacks on contradictions.
2. **Task Queueing:** Move from synchronous Python calls to an asynchronous task queue (e.g., Celery/Redis or async TaskGroup) with heartbeat reporting to the UI/CLI.

---

## 4. The Multi-Modal Pipeline: Fiction -> Script -> Video

To fulfill the vision of a comprehensive narrative universe, the IDE will support a **Script Mode** and a **Video Generation Flow**.

### Workflow:
1. **Import & Structuralize:** User imports raw fiction. Agent structuralizes it into `entities`, `chapters`, and `scenes`.
2. **Fiction Modification:** User and AI collaborate to refine the prose and logic.
3. **Script Transformation (`ScriptAdapterAgent`):**
   - User triggers "Transform to Script".
   - AI translates prose into a structured Screenplay format (e.g., Fountain syntax or structured JSON: `[Character]: [Dialogue] (Action)`).
   - Preserves logical links to the original `Scene` IDs for bi-directional syncing.
4. **Script Modification:** User edits the script natively in the IDE.
5. **Video Generation (`DirectorAgent`):**
   - **Pre-production:** Agent reads Entity descriptions to generate consistent visual prompts (or LoRA triggers).
   - **Production:** Agent breaks script into shot-lists, generating sequential Stable Video Diffusion (or 3rd party API) prompts.
   - **Assembly:** Compiles shots into episodes mapping back to the project structure.

---

## 5. Actionable Development Roadmap

### Phase 1: Ingestion & Massive Scale (The Foundation)
- [ ] Develop `TextParserAgent` to ingest massive `.txt` files and automatically populate `entities/` and `writing/`.
- [ ] Implement Map-Reduce summarization in `context_builder.py` to prevent token limits on 100+ chapter projects.
- [ ] Build global CLI commands (e.g., `fiction-writer refactor --entity "Prince" --global`).

### Phase 2: Autonomous Endurance (The Engine)
- [ ] Refactor `workflow.py` to support asynchronous, interruptible "hours-long" runs.
- [ ] Implement the `ConsistencyEngine` as a background watchdog that validates logic after every scene generation.

### Phase 3: GUI Completion & UX (The Interface)
- [ ] Connect the React frontend to the Python backend streams.
- [ ] Implement virtualized lists in the UI to handle 500+ chapter items without freezing.

### Phase 4: Script & Video Modalities (The Expansion)
- [ ] Create the `ScriptAdapter` module to convert Fiction AST (Abstract Syntax Tree) to Script AST.
- [ ] Build the Video Prompt Generator and integrate with external generation APIs.
- [ ] Add the "Director's Dashboard" UI for episode management.
