import streamlit as st
import os
import sys
from pathlib import Path

# Fix path issues
root_path = Path(__file__).parent.parent.parent
if str(root_path) not in sys.path:
    sys.path.insert(0, str(root_path))

from src.ai.workflow import NarrativeWorkflow
from src.core.persistence import ProjectMemory

# Import Modular Pages
try:
    from src.ui.pages import (
        workbench,
        timeline,
        background_settings,
        characters,
        relationships,
        project_structure,
        chapter_preview,
        chat_assistant,
        map,
        prompts
    )
except ImportError as e:
    st.error(f"Page Import Error: {e}")

# ----------------- Configuration & Styling -----------------
st.set_page_config(page_title="Narrative Lab", layout="wide")

def load_css():
    css_path = os.path.join(os.path.dirname(__file__), "style.css")
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

load_css()

# ----------------- State Initialization -----------------
# Ensure a consistent memory object in session state
if "nl_memory" not in st.session_state:
    st.session_state.nl_memory = ProjectMemory()

memory = st.session_state.nl_memory

# ----------------- Sidebar Routing -----------------
pages = [
    "app",
    "chapter preview",
    "project structure",
    "timeline",
    "characters",
    "relationships",
    "map",
    "background settings",
    "chat assistant",
    "Prompt Management"
]

with st.sidebar:
    st.title("Narrative Lab")
    st.caption("v0.2.8 | Stability Engine")
    st.write("---")
    
    selected_page = st.radio(
        "Navigation",
        pages,
        key="nl_page"
    )
    
    st.write("---")
    if st.button("Force Save & Reload", use_container_width=True):
        memory.save()
        st.session_state.nl_memory = ProjectMemory() # Force full reload
        st.success("JSON Persisted & Normalized.")
        st.rerun()

# ----------------- Page Dispatcher -----------------

def show_settings_header():
    with st.expander("LLM & Language Settings"):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.session_state["openai_api_key"] = st.text_input("OpenAI API Key", value=st.session_state.get("openai_api_key", ""), type="password")
        with col2:
            st.session_state["openai_model"] = st.selectbox("Model", ["gpt-4o-mini", "gpt-4o", "o3-mini"], index=0)
        with col3:
            st.session_state["creative_language"] = st.selectbox("Language", ["English", "Chinese", "Japanese"], index=0)

if selected_page == "app":
    show_settings_header()
    workflow = NarrativeWorkflow(
        api_key=st.session_state.get("openai_api_key"),
        model=st.session_state.get("openai_model", "gpt-4o-mini"),
        language=st.session_state.get("creative_language", "English")
    )
    workbench.render_workbench(memory, workflow)

elif selected_page == "chapter preview":
    chapter_preview.render(memory)
elif selected_page == "project structure":
    project_structure.render(memory)
elif selected_page == "timeline":
    timeline.render(memory)
elif selected_page == "characters":
    characters.render(memory)
elif selected_page == "relationships":
    relationships.render(memory)
elif selected_page == "map":
    map.render(memory)
elif selected_page == "background settings":
    background_settings.render(memory)
elif selected_page == "chat assistant":
    show_settings_header()
    chat_assistant.render(memory)
elif selected_page == "Prompt Management":
    prompts.render(memory)
