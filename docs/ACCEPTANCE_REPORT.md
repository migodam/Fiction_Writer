# Acceptance Report

## 本轮目标
本轮目标是把 Narrative IDE 从“基础壳层 + 部分模块可用”推进到一个**可验收的前端 demo**，满足以下要求：
- 从新建项目开始完成项目初始化
- 支持 Starter Demo Project
- 支持中英文单语言切换
- 支持可折叠 Sidebar 和可调宽的 Sidebar / Inspector / Agent Dock
- 所有主页面都能演示
- 核心跨页链路真实打通
- 提供完整的 demo walkthrough 和验收汇报

## 本轮实现范围
### 壳层与设置
- 完成 `Sidebar / Workspace / Inspector / Agent Dock` 的 IDE 壳层布局
- 支持左侧 Sidebar 折叠/展开
- 支持 `Sidebar / Inspector / Agent Dock` 拖拽调宽
- 增加 `Settings` 面板
- 增加 `language switch` 与 `layout reset`

### 项目初始化与本地后端能力
- 增加本地项目服务层，负责：
  - `createProject`
  - `openProject`
  - `saveProject`
  - `exportProject`
  - `importAsset`
- 项目模型支持：
  - `blank` 模板
  - `starter-demo` 模板
- Electron 侧增加目录选择 IPC
- 浏览器模式保留 localStorage 回退路径，便于 Playwright 验证

### Starter Demo Project
预置了一套富内容演示工程，包括：
- 5 个正式角色 + 1 个候选角色
- 多个地点、组织、物品、设定
- 3 条 timeline branch
- 2 个 chapter、6 个 scene
- 1 个混合 graph board
- 已有 proposals / history / issues
- 可导出的 publish 数据
- 世界地图底图和 marker

### 主要模块完成情况
- `Workbench`：Inbox / History / Issues / Bulk 可用
- `Characters`：档案、候选确认、画像位、生日、组织、状态标记、跨页跳转可用
- `Timeline`：branch、人物筛选、地点筛选、事件跳 scene 可用
- `Writing Studio`：chapter/scene、正文编辑、自动保存、上下文面板可用
- `World Model`：默认容器、自定义容器、条目编辑、世界地图 marker 可用
- `Graph`：混合节点展示、选择节点、发送 proposal 到 Workbench 可用
- `Consistency`：问题列表 + 修复建议送入 Workbench 可用
- `Simulation / Beta Reader / Insights`：升级为 data-backed demo
- `Publish`：Markdown / HTML 导出与历史记录可用

## 必要后端改动说明
### Electron 侧
- 新增目录选择能力，供项目新建/打开流程使用
- 保持 Electron 负责 shell 和文件系统桥接，不把文件 IO 混入 React 组件

### 项目服务层
- 以 repository/service 思路收口项目读写逻辑
- React 侧通过 store 和 service 使用项目数据，不直接散读原始文件
- 支持导出产物记录、提案生命周期、资产导入和项目模板初始化

## UI / 交互改动说明
### 语言切换
- 当前是**中英文单语言切换**
- 一次只显示一种语言
- 路由保持英文，不做中文 URL
- 用户输入内容不参与翻译

### 布局
- 顶层采用更接近桌面 IDE 的三栏 + Agent Dock 结构
- Activity Bar 保持固定宽度
- Sidebar 可折叠
- Inspector 与 Agent Dock 保留固定区域感，但支持拖拽调宽

### Agent 预留
- 保留 `Agent Dock + Workbench` 双层结构
- 不接真实 agent
- 不实现浮动 agent 窗口
- 后续接入 CLI/agent 时，不需要推翻当前主界面结构

## 核心跨页联动清单
- `Characters -> Timeline`：人物详情可打开该人物过滤时间线
- `Characters -> Graph`：人物详情可跳关系图
- `World Model -> Timeline`：地点条目和地图 marker 可打开地点过滤时间线
- `Timeline -> Writing`：事件可跳到关联 scene
- `Graph -> Workbench`：图板选择可发 proposal
- `Consistency -> Workbench`：修复建议转 proposal
- `Workbench -> History`：接受/拒绝后进入历史并清理未读
- `Publish <- Project data`：导出基于当前项目结构和附录选项

## walkthrough 覆盖范围
配套文档 [DEMO_WALKTHROUGH.md](/d:/NUS/Computing/Projects/Fiction_Writer/docs/DEMO_WALKTHROUGH.md) 覆盖了：
- 新建项目
- Starter Demo Project
- 语言切换
- 布局调节
- Workbench
- Characters
- Timeline 分支与筛选
- Writing Studio
- World Model 全容器
- World Map
- Graph proposal flow
- Workbench review flow
- Consistency
- Simulation
- Beta Reader
- Publish
- Insights
- 保存并重新打开项目

## 已通过测试
### 构建
- `npm run build`

### Playwright
- `npm run test:e2e`
- 当前结果：`30/30 passed`

覆盖范围包括：
- P0：导航、人物 CRUD、时间线事件、写作自动保存
- P1：
  - 项目初始化与重开
  - 布局与语言切换
  - Characters 路由契约
  - World Model 容器与地图
  - Graph -> Workbench
  - Cross-page deep links
  - Publish 导出
  - Smoke 全流程

## 验收建议顺序
建议实际验收时按下面顺序看：
1. 新建 Starter Demo Project
2. 切换语言
3. 折叠和调宽布局
4. Characters
5. Timeline
6. Writing
7. World Model
8. Graph
9. Workbench
10. Consistency
11. Publish
12. 保存并重新打开项目

## 本轮修掉的关键问题
- 旧测试仍绑定旧 seed ID，导致 candidate / character / graph / writing 路径全错位
- 侧栏折叠按钮存在实际逻辑缺陷，按钮没有真正切换折叠状态
- Starter project、世界地图、发布模块缺乏验收覆盖
- 命令面板和跨页测试仍依赖旧文案/旧 locator 契约

## 已知限制
- 浏览器模式下的项目生命周期仍然使用 localStorage 回退；真实目录体验依赖 Electron 模式
- 当前没有真实 agent 执行能力，`Agent Dock` 只是未来兼容壳层
- 画像生成按钮是占位功能，不会调用图像生成服务
- Simulation / Beta Reader / Insights 仍是高质量 demo，不是最终智能分析系统
- 还没有撤销/版本管理等高阶能力

## 下一阶段建议
1. 把 Electron 目录流程做成真实的 end-to-end 桌面验收链路
2. 增强角色、场景、事件、世界条目的双向引用可视化
3. 深化 Graph 的编辑能力，不只展示和发 proposal
4. 把 Publish 输出落到真实工程目录，并增加导出配置细节
5. 在保留当前壳层前提下接入真正的 agent task runner
