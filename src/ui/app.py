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
if "nl_memory" not in st.session_state:
    st.session_state.nl_memory = ProjectMemory()

memory = st.session_state.nl_memory

# ----------------- Sidebar Routing -----------------
def get_sidebar_labels(mem):
    labels = {
        "app": "Workbench",
        "chapter preview": "Manuscript",
        "outline & structure": "Outline",
        "timeline": "Timeline",
        "characters": "Characters",
        "relationships": "Relationships",
        "map": "World Map",
        "background settings": "Notebook",
        "chat assistant": "Assistant",
        "Prompt Management": "Settings"
    }
    
    # Check for updates in each section
    data = mem.data
    updates = {
        "outline & structure": any(o.get("ui_metadata", {}).get("is_new_update") for o in data.get("outline", [])),
        "timeline": any(e.get("ui_metadata", {}).get("is_new_update") for e in data.get("timeline_events", [])),
        "characters": any(c.get("ui_metadata", {}).get("is_new_update") for c in data.get("characters", [])),
        "background settings": any(p.get("ui_metadata", {}).get("is_new_update") for p in data.get("setting_pages", [])) or \
                              any(any(it.get("ui_metadata", {}).get("is_new_update") for it in p.get("items", [])) for p in data.get("setting_pages", []))
    }
    
    final_labels = {}
    for k, v in labels.items():
        if updates.get(k):
            final_labels[k] = f"{v} ✨"
        else:
            final_labels[k] = v
    return final_labels

sidebar_map = get_sidebar_labels(memory)
inv_sidebar_map = {v: k for k, v in sidebar_map.items()}

with st.sidebar:
    st.title("Narrative IDE")
    st.caption("v0.3.8 | Professional")
    st.write("---")
    
    selected_label = st.radio(
        "Navigation",
        list(sidebar_map.values()),
        key="nl_page_label"
    )
    selected_page = inv_sidebar_map[selected_label]
    
    st.write("---")
    if st.button("Force Save & Reload", use_container_width=True):
        memory.save()
        st.session_state.nl_memory = ProjectMemory()
        st.success("JSON Persisted.")
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
elif selected_page == "outline & structure":
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
