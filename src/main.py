import streamlit as st
import os

# App Title
st.set_page_config(page_title="Fiction Writer - 纯本地 AI 小说创作助手", layout="wide")

st.title("Fiction Writer - 纯本地 AI 小说创作助手")

# Sidebar for Configuration
with st.sidebar:
    st.header("创作设置")
    llm_model = st.selectbox("选择 AI 模型", ["Ollama (Llama 3)", "Ollama (Mistral)", "Llama-CPP (Local GGUF)"])
    temperature = st.slider("创意度 (Temperature)", 0.0, 1.0, 0.7)

# Main Writing Area
col1, col2 = st.columns([2, 1])

with col1:
    st.header("创作面板")
    title = st.text_input("章节标题", "第一章：新的开始")
    content = st.text_area("写作内容", height=500, placeholder="在此开始创作...")

with col2:
    st.header("AI 辅助")
    task = st.selectbox("选择辅助任务", ["续写下一段", "润色选中文字", "情节推演", "角色性格分析"])
    if st.button("开始 AI 处理"):
        st.info("AI 正在思考中... (目前尚未接入后端)")

# Status Bar
st.divider()
st.caption("Fiction Writer v0.1.0 | 运行模式: 本地 (Local-First)")
