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

---

## 6. PM Requirements / Frontend Restructure (2026-03-18)

以下内容作为当前前端产品层重构的正式约束，优先级高于旧的 demo 式页面拼接逻辑。

### 6.1 信息架构原则
- 二级导航只用于真正不同的功能分区，不允许和三级导航重复表达同一页面。
- 三级导航只用于当前分区内的实体列表、筛选或上下文，不再复刻一个完整页面。
- 页面不能存在“点第二个第三个还停在第一个”的错误导航；这类情况视为实现缺失。
- 所有工作区必须保证“可新建、可编辑、可保存、可再次打开”，不允许只展示静态示例。

### 6.2 Timeline 交互原则
- Timeline 主视图采用单工作区，不再保留仅有一个入口的冗余二级导航。
- Event 在主画布上只显示为点，不直接展开全文内容。
- 点的颜色表示重要程度；hover 显示概览，click 打开悬浮窗显示详情。
- 右侧大面积 selection panel 取消，详情统一使用 modal / popover / drawer 浮层。
- Event 支持前后拖动重排，也支持拖到其他 branch 并吸附到合法槽位。
- 吸附规则必须保证事件不重合；若落点会与其他事件重叠，则该落点非法。
- 新建 Event 默认插入当前 branch、当前 event 的后一个位置；若未选中 event，则插入 branch 末尾。
- Timeline 允许 branch 线条几何变形，不同 branch 不要求长度相同。

### 6.3 Timeline Branch 生命周期
- Branch 创建有两种模式：
  - 独立开始：无父 branch，可单独演进。
  - 从现有 event 分叉：在选中 event 上创建 fork，记录 start anchor。
- Branch 结束有三种模式：
  - open：继续开放延伸。
  - closed：独立结束，不合流回其他线。
  - merge：指定 merge target branch，并在目标位置形成合流。
- Branch 的几何拖动只改变视觉布局，不改变 event 顺序。
- Event 的拖动改变 branch / slot，不自动重写其他 branch 几何。

### 6.4 Characters / Relationships 原则
- 人物列表默认按重要性分组，支持折叠展开，以适应大量角色。
- 三级导航下的人物概览只显示名字，不展示冗长描述。
- 单人物页顶部固定为：档案 / 关系 / 时间线 / POV Insights。
- 单人物页的 relationship 列表和全局 relationship graph 必须共享同一份关系数据。
- Tag 只显示已拥有的 tag，通过 `+` 执行添加或新建，不展示大量灰色未命中 tag。
- POV Insights 页面允许展示 AI 生成结果，也允许明确显示“尚未生成”的占位态。

### 6.5 World Model 原则
- World Model 二级导航固定为：`entries / map / settings`。
- `entries` 承担世界条目、地点、组织、规则、物件等列表与容器管理。
- `map` 支持多个世界地图，允许新建、切换与 marker 编辑。
- `settings` 存放作品类型、叙事节奏、语言风格、世界规则摘要等全局设定。

### 6.6 Simulation / Reviewer 原则
- Simulation 允许多个 lab；每个 lab 下允许多个 engine。
- Engine 至少包括：scenario / character / author / reader / logic / custom。
- Reviewer 复用 engine 架构，但目标改为检查、指出问题、评分，而不是预测剧情。
- Lab / Reviewer 的 overview 支持一键运行本容器下所有 engine，并汇总结果。
- 每个 engine 均允许用户补写 prompt override。

### 6.7 Writing / Import / Export 原则
- Writing 必须支持手动创建 chapter、scene、script、storyboard，并立即进入可编辑状态。
- 系统需要能承载上千章小说，因此长列表必须支持分组、折叠、搜索、增量渲染。
- Import 页面必须是完整交互流程：选择文件、配置、预览、确认导入、查看 review proposal。
- Export 除整本导出外，还必须支持按章节范围导出。

### 6.8 Settings 原则
- Settings 不是展示型页面，所有选项都必须真正生效。
- Settings 至少划分：
  - workspace
  - writing
  - providers
  - models
  - import-export
  - appearance
  - advanced
- API key、provider endpoint、模型偏好属于应用级配置，不写入项目 canonical storage。
- 项目内只保存 provider / model profile 的引用，不保存密钥明文。

### 6.9 当前实现准则
- 当前轮次重点是前端产品层闭环与可用性，不新增 agent workflow 能力范围。
- 已有 v4 project-folder backend 继续保留，作为未来 agent / LangGraph / CLI 的数据边界。
- 前端任何 placeholder 都必须明确标注为 placeholder，不能伪装成已接入真实 AI 服务。
