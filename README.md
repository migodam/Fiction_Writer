# Fiction Writer - 纯本地 AI 小说创作助手

本项目旨在构建一个完全运行在本地的 AI 小说创作助手，利用大语言模型（LLM）协助作家进行大纲构思、情节生成、角色设计以及全文润色。

## 功能特点

- **全本地运行**：通过 Ollama 或本地加载的 GGUF 模型运行，确保创作内容的绝对隐私。
- **长文本支持**：优化长文档的创作流程，支持章节管理。
- **角色关系图**：可视化管理小说中的人物及其复杂关系。
- **自动情节衔接**：基于前文自动推演后续情节逻辑。

## 开发进度

- [x] 项目结构初始化
- [ ] 本地 AI 推理后端集成 (Ollama/llama-cpp-python)
- [ ] 前端界面开发 (Streamlit / Electron)
- [ ] 知识库/设定集管理系统

## 快速开始

### 1. 环境准备

确保您的电脑已安装 Python 3.10+。

### 2. 创建并激活虚拟环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. 安装依赖

```powershell
pip install -r requirements.txt
```

### 4. 运行程序

*(待后续开发完善)*

## 许可证

MIT License
