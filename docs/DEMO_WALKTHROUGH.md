# Narrative IDE Demo Walkthrough

## 目的
这份文档按“第一次上手”的方式，带你从**新建项目**开始，完整体验当前 Narrative IDE demo 的主要功能、跨页联动、布局能力、语言切换和导出流程。

建议你严格按顺序体验。这样能最清楚地看到：
- 项目初始化是否正常
- 各页面是否不是空壳
- 人物、时间线、写作、世界模型、图板、工作台之间是否真正打通
- 中英文切换、侧栏折叠、面板调宽、右键菜单这些桌面 IDE 能力是否可用

## 运行前准备
### 推荐运行方式
优先使用 Electron 开发模式：

```powershell
npm run electron:dev
```

这样你可以体验真实的项目目录选择流程。

### 浏览器回退方式
如果你只想快速看前端，也可以用：

```powershell
npm run dev
```

然后打开 `http://localhost:3000`。

说明：
- Electron 模式下，`新建项目/打开项目` 会走真实目录选择。
- 浏览器模式下，项目数据会回退到本地浏览器存储，用来完成前端演示和测试。

## 建议体验顺序
1. 新建项目并选择 Starter Demo Project
2. 切换语言
3. 调整布局：收起左栏、拉宽各面板、重置布局
4. 看 Workbench
5. 看 Characters
6. 看 Timeline
7. 看 Writing Studio
8. 看 World Model
9. 看 Graph
10. 回到 Workbench 审核 Proposal
11. 看 Consistency
12. 看 Simulation
13. 看 Beta Reader
14. 看 Publish
15. 看 Insights
16. 保存并重新打开项目

---

## 1. 新建项目
### 你要做什么
1. 启动应用。
2. 点击顶部工具栏左侧的 `New Project` / `新建项目` 按钮。
3. 在弹出的项目窗口里：
   - `Project Name / 项目名称` 输入：`Acceptance Starter`
   - `Template / 初始化模板` 选择：`Starter Demo Project / 演示模板项目`
4. 如果你当前在 Electron 模式：
   - 点击 `Choose Folder / 选择目录`
   - 选择一个空目录或父目录
5. 点击 `Create Project / 创建项目`

### 你应该看到什么
- 状态栏里的项目名变成 `Acceptance Starter`
- 应用主界面加载一套已经有内容的 demo 工程
- 左侧 Activity Bar、Sidebar、主工作区、Inspector、右侧 Agent Dock 都可见

### 这一步验证了什么
- 项目初始化流程存在，不是死数据页面
- Starter Demo Project 能直接生成一个可演示工程
- 主壳加载的是“项目”，不是一堆孤立的静态组件

### 如果你没看到预期结果
- 检查项目弹窗是否还开着
- Electron 模式下确认你选了目录
- 浏览器模式下如果目录为空是允许的，这是前端回退逻辑

---

## 2. 体验语言切换
### 你要做什么
1. 点击右上角 `Settings / 设置`
2. 在 `Language / 语言` 区域：
   - 先点 `中文`
   - 观察界面后再点回 `English`
3. 关闭设置窗口

### 你应该看到什么
切成中文后：
- `Workbench` 变成 `工作台`
- 侧栏、状态栏、主页面标题等主要文案变成中文

切回英文后：
- 主界面再回到英文
- 路由 URL 不变，仍然是英文路径

### 这一步验证了什么
- 当前应用是**单语言切换**，不是双语同时显示
- 文案切换覆盖的是主壳和主要工作流，不只是少量按钮

---

## 3. 体验 IDE 布局
### 3.1 收起左侧栏
#### 你要做什么
点击顶部工具栏的 `Toggle Sidebar / 切换侧栏`

#### 你应该看到什么
- 左侧 Sidebar 收起
- 主工作区变宽
- 再点一次，Sidebar 展开

#### 这一步验证了什么
- 你可以像 VS Code 一样把主要空间让给工作区

### 3.2 调整 Sidebar 宽度
#### 你要做什么
- 把鼠标移动到 Sidebar 和主工作区之间的竖向分隔条
- 左右拖动

#### 你应该看到什么
- 左栏宽度随拖动变化
- 工作区宽度同步变化

### 3.3 调整 Inspector 宽度
#### 你要做什么
- 把鼠标移动到主工作区和 Inspector 之间的分隔条
- 左右拖动

#### 你应该看到什么
- Inspector 宽度变化
- 右侧细节查看空间更大或更小

### 3.4 调整 Agent Dock 宽度并折叠
#### 你要做什么
1. 拖动 Inspector 和 Agent Dock 之间的分隔条
2. 点击右上角 `Bot` 图标
3. 再点击 Agent Dock 上的展开按钮

#### 你应该看到什么
- Agent Dock 宽度可调
- 折叠后右侧只保留一个窄条入口
- 展开后恢复完整面板

### 这一步验证了什么
- 当前应用已经具备桌面 IDE 的基本布局管理能力
- 后续接 agent 时不会和主编辑区冲突

### 3.5 体验 Settings 的完整布局项
#### 你要做什么
1. 点击 `Settings / 设置`
2. 依次调整：
   - `Density`
   - `Editor Width`
   - `Motion`
3. 点击 `Reset Layout`

#### 你应该看到什么
- 显示偏好会即时生效
- Reset Layout 会恢复顶层和 Writing Studio 的默认布局
- Settings 已经不仅仅是语言切换入口

---

## 4. Workbench：提案与问题中枢
### 你要做什么
点击左侧 Activity Bar 的 `Workbench / 工作台`

### 4.1 Inbox
#### 你要做什么
1. 保持在 `Inbox / 收件箱`
2. 找到标题为：`Convert public fallout note into timeline candidate` 的提案
3. 阅读卡片中的说明和预览内容

#### 你应该看到什么
- 这里有 `graph` 或 `consistency` 来源的 proposal
- 每张卡片有 `Accept` / `Reject` 按钮

### 4.2 History
#### 你要做什么
点击侧栏 `History / 历史`

#### 你应该看到什么
- 已经处理过的 proposal 进入历史区
- 历史区不会再显示未读提醒逻辑

### 4.3 Issues
#### 你要做什么
点击侧栏 `Issues / 问题`

#### 你应该看到什么
- 当前 starter project 自带一致性问题
- 例如 `Bridge location mismatch`
- 每个问题会显示严重级别和修复建议

### 4.4 Bulk Actions
#### 你要做什么
点击侧栏 `Bulk Actions / 批量操作`

#### 你应该看到什么
- 有 `Queue Sync`
- 有 `Retry`
- 有 `Archive Seen`
- 这是未来 agent 批处理入口预留区，不是聊天窗口

### 这一步验证了什么
- Workbench 不是占位页，而是全局审核中枢
- Graph、Consistency 未来都可以把结果统一路由到这里

---

## 5. Characters：人物主档案
### 5.1 看已有角色
#### 你要做什么
点击 `Characters / 人物`

#### 你应该看到什么
- 左侧人物列表中能看到多个角色
- 至少包括：
  - `Aria Solis`
  - `Rowan Vale`
  - `Seren Holt`
  - `Vesper Noct`
  - `Nila Quill`

### 5.2 查看角色详情
#### 你要做什么
点击 `Aria Solis`

#### 你应该看到什么
- 档案页里有：
  - name
  - background
  - aliases
  - traits
  - birthday
  - organization
  - status flags
  - portrait slot
- 页面底部有：
  - 打开人物时间线
  - 打开关系图
  - 保存

### 5.3 体验人物画像位
#### 你要做什么
在人物详情页找到画像区：
- 点 `Upload Portrait`
- 点 `Generate Portrait`

#### 你应该看到什么
- 上传按钮会打开文件选择
- 生成按钮目前是占位动作，不会真的生成图像，但会给出状态反馈

### 5.4 看人物关系页
#### 你要做什么
点击 `Relationships` Tab

#### 你应该看到什么
- 关系网络面板
- 可以新增关系卡片
- 能看到关系结构不是空的
- 右键关系卡会出现上下文菜单

### 5.5 看人物时间存在页
#### 你要做什么
点击 `Timeline` Tab

#### 你应该看到什么
- 会显示该人物相关的事件/时间存在信息

### 5.6 看人物标签页
#### 你要做什么
点击 Sidebar 的 `Tags`

#### 你应该看到什么
- 角色标签管理页不是空白页
- 可以创建 tag
- 可以把 tag 分配给不同角色
- 删除 tag 后，角色档案里的 tag 会同步更新

### 5.7 新建一个角色
#### 你要做什么
1. 点击 `new-character-btn`
2. 填写：
   - 名称：`Field Observer Lin`
   - 背景：`Archive runner assigned to verify bridge witnesses.`
   - 可再填写生日、组织、状态标记
3. 点击保存

#### 你应该看到什么
- 新角色出现在人物列表里
- 状态栏里出现当前选中的角色名

### 5.8 看候选角色
#### 你要做什么
点击 Sidebar 的 `Candidate Queue / 候选队列`

#### 你应该看到什么
- 可以看到 `Mina Vale`
- 每个候选卡片有：
  - `Confirm`
  - `Reject`

### 5.9 确认候选角色
#### 你要做什么
点击 `Mina Vale` 卡片上的 `Confirm`

#### 你应该看到什么
- 页面跳到 `/characters/profile/cand_mina`
- 角色被加入人物列表
- 说明“AI 或系统提案进入人工确认后，才进入正式项目数据”这条规则生效

### 这一步验证了什么
- 人物模块不是只展示名字，而是有完整档案、候选确认、关系、跨页跳转入口

---

## 6. Timeline：分支、人物筛选、地点筛选、跳场景
### 6.1 看主时间线
#### 你要做什么
点击 `Timeline / 时间线`

#### 你应该看到什么
- 页面顶部有筛选条
- 中间按 branch 展示多条事件轨道
- 默认能看到这些 branch：
  - `Main Investigation`
  - `Shadow Routes`
  - `Public Pressure`

### 6.2 理解为什么有分支
#### 你要做什么
观察每一条 branch 的标题和事件

#### 你应该看到什么
- 不同分支承载不同叙事线程
- shared event 会出现在多个 branch 上
- branch 会显示 fork 来源，不再只是平行轨道假分支

### 6.3 体验时间线缩放和平移
#### 你要做什么
1. 在时间线上按住空白处拖动
2. 使用顶部缩放控件
3. 或按住 `Ctrl + 滚轮` 缩放

#### 你应该看到什么
- 时间线支持平移
- 时间线支持缩放
- hover 节点时可以看到事件预览卡

### 6.4 切换 branch 视图
#### 你要做什么
在顶部 `timeline-branch-filter` 下拉框中选择：
- `Main Investigation`
- 再切换到 `Shadow Routes`

#### 你应该看到什么
- 事件轨道会根据 branch 变化
- 上方 `timeline-filter-state` 会明确告诉你当前正在看哪个 branch

### 6.5 按人物查看 timeline
#### 你要做什么
1. 回到 `Characters`
2. 点 `Aria Solis`
3. 点击底部 `Timeline / 时间线`

#### 你应该看到什么
- 自动跳转到 `/timeline/events?character=char_aria`
- `timeline-filter-state` 中显示按人物筛选
- 事件列表只保留 Aria 参与的事件

### 6.6 按地点查看 timeline
#### 你要做什么
1. 点击 `World Model`
2. 打开 `Locations`
3. 选择 `Glass Bridge`
4. 点击 `View Timeline / 查看时间线`

#### 你应该看到什么
- 自动跳转到 `/timeline/events?location=loc_glass_bridge`
- `timeline-filter-state` 显示当前按地点筛选
- 只显示发生在 `Glass Bridge` 的事件

### 6.7 从时间线跳到写作场景
#### 你要做什么
1. 在时间线上点击 `Bridge Intercept`
2. 点击卡片上的 `Open Linked Scene / 打开关联场景`

#### 你应该看到什么
- 跳转到 `Writing Studio`
- 当前场景标题是 `Glass Bridge Intercept`
- 说明时间线和写作不是断开的

### 6.8 新建一个事件
#### 你要做什么
1. 点击 `Add Event / 新增事件`
2. 在 Inspector 里填写：
   - Title：`Witness Recall`
   - Summary：`A delayed witness statement reframes the bridge handoff.`
3. 点击保存

#### 你应该看到什么
- 新事件进入当前 timeline
- Inspector 和 Timeline 之间数据是打通的

### 这一步验证了什么
- Timeline 支持分支
- Timeline 支持按人物/地点看事件
- Timeline 能跳转到 Writing
- Timeline 不是简单静态列表

---

## 7. Writing Studio：章节、场景、上下文联动
### 7.1 看章节与场景结构
#### 你要做什么
点击 `Writing Studio`

#### 你应该看到什么
- 左边是可折叠、可调宽的 `Outline / Selection`
- 至少有两章
- 每章下有多个 scene

### 7.2 打开场景
#### 你要做什么
点击 `Dockside Arrival` 或 `Glass Bridge Intercept`

#### 你应该看到什么
- 中间是正文编辑器
- 上方显示：
  - POV
  - Events
  - World

### 7.3 看右侧上下文面板
#### 你要做什么
观察右侧 `Narrative Context`

#### 你应该看到什么
- Characters 列表
- Events 列表
- World 条目列表
- 已链接内容和最近活跃内容会同时出现
- 不是静态说明，而是来自项目数据

### 7.4 体验 Writing 内部分栏
#### 你要做什么
1. 拖动正文左侧和右侧的分隔条
2. 折叠 Outline
3. 折叠 Context
4. 再重新展开

#### 你应该看到什么
- `Outline / Manuscript / Context` 三栏都可以独立调宽
- 左右两侧都可以独立收起
- 页面不会再出现明显的双滚动条冲突

### 7.5 修改正文并保存
#### 你要做什么
在正文里追加一段英文或中文内容，停顿 1-2 秒

#### 你应该看到什么
- 会触发自动保存反馈
- 状态栏或 toast 会显示 `Saved / 已保存`

### 7.6 从上下文点击人物
#### 你要做什么
在右侧上下文人物里点击一个角色，例如 `Aria Solis`

#### 你应该看到什么
- 当前选中对象切换为该角色
- 状态栏 Selection 更新

### 这一步验证了什么
- Writing 不是孤立富文本框
- Scene 与人物、事件、世界条目是真实联动的

---

## 8. World Model：地点、组织、物品、设定、地图
### 8.1 查看 Locations
#### 你要做什么
点击 `World Model`，在容器列表中选择 `Locations`

#### 你应该看到什么
- 可见多个地点条目
- 如 `Sky Dock`、`Glass Bridge` 等

### 8.2 查看 Organizations
#### 你要做什么
在容器列表里点 `Organizations`

#### 你应该看到什么
- 组织条目，例如和主线调查有关的组织

### 8.3 查看 Items
#### 你要做什么
在容器列表里点 `Items`

#### 你应该看到什么
- 可以看到物品条目，例如关键 artifact

### 8.4 查看 Lore
#### 你要做什么
在容器列表里点 `Lore`

#### 你应该看到什么
- 世界设定条目
- 这些设定可被 Timeline / Writing / Graph 引用

### 8.5 打开 World Map
#### 你要做什么
点击 `Maps / 地图` 或直接路由 `World Map`

#### 你应该看到什么
- 地图底图显示出来
- 上面有多个 marker
- marker 代表与 location/world 数据绑定的位置

### 8.6 点击 marker
#### 你要做什么
点击任意地图 marker

#### 你应该看到什么
- 会跳到该地点对应的 timeline 过滤视图

### 8.7 新建自定义容器和条目
#### 你要做什么
1. 点击 `create-container-btn`
2. 观察新容器会直接进入 rename 态
3. 在新容器里点击 `add-world-item-btn`
4. 新建一个条目，例如：
   - Name：`Witness Ledger`
   - Description：`Recovered list of courier exchanges.`
5. 用 `dynamic-field-add-row` 增加一个属性
6. 保存

#### 你应该看到什么
- 新容器、新条目都能被创建和保存
- 容器支持 rename 和 collapse
- 说明 World Model 不是只读配置区

### 这一步验证了什么
- World Model 已具备默认容器 + 自定义容器
- World Map 不是装饰图，而是带 marker 和跳转能力的页面

---

## 9. Graph：自由草图和结构化引用共存
### 9.1 打开图板
#### 你要做什么
点击 `Graph`

#### 你应该看到什么
- 左侧有多个 board，可切换
- 图板里同时存在多种对象：
  - `character_ref`
  - `event_ref`
  - `location_ref`
  - `world_item_ref`
  - `image_card`
  - `free_note`
  - `group_frame`

### 9.2 识别不同卡片类型
#### 你要做什么
逐个点击图板上的卡片

#### 你应该看到什么
- 不同类型的卡片视觉不同
- 说明图板不是单一节点样式

### 9.3 试用图板工具按钮
#### 你要做什么
依次点击：
- `graph-add-node-btn`
- `graph-add-edge-btn`
- `graph-auto-layout-btn`
- `graph-reset-layout-btn`

#### 你应该看到什么
- Auto Layout / Reset 会给出状态反馈
- 当前图板具备基本交互反馈，不是纯图片
- 可拖动节点
- 可拖动画布
- `Ctrl + 滚轮` 可以缩放

### 9.4 新建一个 board
#### 你要做什么
点击左上角的 `graph-create-board-btn`

#### 你应该看到什么
- 左侧 board 列表新增一个空 board
- 当前激活 board 自动切换到新 board
- 右键 board 会出现上下文菜单

### 9.5 从图板发起 proposal
#### 你要做什么
1. 选中 `Aria Solis` 对应节点
2. 点击 `graph-sync-selection-btn`

#### 你应该看到什么
- 出现 `Proposal queued`
- 说明 Graph 的 AI/同步结果不会直接改 canonical data，而是进入待审核流程

### 这一步验证了什么
- Graph 允许自由草图对象和结构化引用长期共存
- Graph -> Workbench 的提案链路是存在的

---

## 10. 回到 Workbench 审核 Graph Proposal
### 你要做什么
1. 点击 `Workbench`
2. 打开 `Inbox`
3. 找到刚刚新增的 `Graph sync batch`
4. 先试一次 `Accept`
5. 再切到 `History`

### 你应该看到什么
- Inbox 数量变化
- History 出现新的已处理项
- 接受/拒绝后不需要你手动再清未读状态

### 这一步验证了什么
- 提案处理生命周期完整：`pending -> accepted/rejected -> history`

---

## 11. Consistency：问题检查与建议修复
### 你要做什么
1. 点击 `Consistency`
2. 点击 `run-consistency-btn`
3. 查看问题列表
4. 选择一个问题，点击对应的“送入 Workbench 修复提案”动作

### 你应该看到什么
- 能看到若干问题，例如：
  - `Bridge location mismatch`
  - 重复条目风险
  - 人物状态标记审查
- 这些问题有描述和 fix suggestion
- fix suggestion 会进入 Workbench，而不是静默改数据

### 这一步验证了什么
- Consistency 不是空壳，而是带数据驱动问题的页面
- 修复建议遵循人工确认流

---

## 12. Simulation：推演入口
### 你要做什么
1. 点击 `Simulation`
2. 选择 `Betrayal at Dawn`
3. 点击 `run-simulation-btn`

### 你应该看到什么
- 中间控制台区域开始运行
- 一段时间后出现 `Simulation complete`

### 这一步验证了什么
- 当前不是接真实 agent，但已经有数据驱动的可交互模拟入口

---

## 13. Beta Reader：模拟读者反馈
### 你要做什么
1. 点击 `Beta Reader`
2. 选择 `The Logician`
3. 点击 `run-beta-reader-btn`

### 你应该看到什么
- 出现 `Beta simulation complete`
- 页面里有 `Engagement`、`Retention`、`Resonance` 等结果卡
- 下方有更像读者反馈的文本条目
- 左侧 persona 列表支持创建新的 beta reader persona
- 右侧还有一个 aggregate panel 汇总多 persona 反馈

### 这一步验证了什么
- Beta Reader 不是空页，已经是可解释的 demo 功能

---

## 14. Publish：导出 Markdown / HTML
### 你要做什么
1. 点击 `Publish`
2. 保持 `Include appendices / 附带附录` 为开启
3. 点击：
   - `Export Markdown`
   - `Export HTML`

### 你应该看到什么
- 右侧预览区显示导出内容
- 左侧导出历史中出现 `.md` 和 `.html` 记录

### 这一步验证了什么
- Publish 已经具备真正的 demo 导出流程
- 附录配置参与导出逻辑

---

## 15. Insights：全局统计
### 你要做什么
点击 `Insights`

### 你应该看到什么
- 角色数量、场景数量、时间线事件数量、世界条目数量
- 下方还有叙事覆盖、世界密度等统计说明

### 这一步验证了什么
- Insights 已经读取真实项目数据，而不是静态文案

---

## 16. 保存并重新打开项目
### 你要做什么
1. 点击顶部 `Save Project / 保存项目`
2. 再点击 `Open Project / 打开项目`
3. 在 Electron 模式下选择刚刚创建的项目目录
4. 在浏览器模式下直接提交打开对话框，加载最近保存项目

### 你应该看到什么
- 项目名仍然是 `Acceptance Starter`
- 你在过程中新增的人物、条目、提案结果仍然存在

### 这一步验证了什么
- 这不是一次性页面体验，而是一个带保存/重开概念的本地项目系统

---

## 重点验收清单
如果你时间有限，可以只检查下面这些：
- 能否从新建项目开始，生成 Starter Demo Project
- 能否中英文切换
- 能否折叠左栏并拖拽三块面板宽度
- Characters -> Timeline 是否能按人物筛选
- World Map -> Timeline 是否能按地点筛选
- Timeline -> Writing 是否能跳关联场景
- Graph -> Workbench 是否能形成 proposal 审核链路
- Publish 是否能产出 Markdown/HTML 记录
- 保存并重新打开后数据是否还在

## 当前 demo 中最值得看的联动
- `Characters -> Timeline`
- `World Model -> Timeline`
- `Timeline -> Writing`
- `Graph -> Workbench`
- `Consistency -> Workbench`
- `Publish <- Project data`

## 已知限制
- 当前还没有真实 agent 执行，只保留了 `Agent Dock + Workbench` 的未来兼容结构
- 浏览器模式下的项目初始化/打开/保存会使用本地存储回退；真实目录操作以 Electron 模式为准
- 人物画像“生成”按钮目前是占位操作，不会调用图像模型
- Simulation / Beta Reader / Insights 目前是高质量 data-backed demo，不是最终的智能分析系统
