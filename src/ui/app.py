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
    from src.ui.pages.workshop import render_workshop_page
    from src.ui.pages.timeline import render_timeline_page
    from src.ui.pages.background_settings import render_background_settings_page
    from src.ui.pages.characters import render_characters_page
    from src.ui.pages.relationships import render_relationships_page
    from src.ui.pages.project_structure import render_project_structure
    from src.ui.pages.chapter_preview import render_chapter_preview
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
if "memory" not in st.session_state:
    st.session_state.memory = ProjectMemory()
if "workflow" not in st.session_state:
    st.session_state.workflow = NarrativeWorkflow(model="llama3.1:8b")
if "nl_nav" not in st.session_state:
    st.session_state.nl_nav = "Narrative Workshop"

memory = st.session_state.memory
workflow = st.session_state.workflow

# ----------------- Unified Sidebar -----------------
# We use standard Streamlit sidebar buttons to control navigation state.
def set_page(name):
    st.session_state.nl_nav = name

with st.sidebar:
    st.title("Narrative Lab")
    st.caption("Creative Production Line")
    
    st.write("---")
    st.markdown("**CREATION**")
    st.button("Narrative Workshop", on_click=set_page, args=("Narrative Workshop",), use_container_width=True)
    
    st.write("---")
    st.markdown("**STRUCTURE**")
    st.button("Project Structure", on_click=set_page, args=("Project Structure",), use_container_width=True)
    st.button("Timeline", on_click=set_page, args=("Timeline",), use_container_width=True)
    st.button("Characters", on_click=set_page, args=("Characters",), use_container_width=True)
    st.button("Relationships", on_click=set_page, args=("Relationships",), use_container_width=True)
    st.button("Background Settings", on_click=set_page, args=("Background Settings",), use_container_width=True)

    st.write("---")
    st.markdown("**OUTPUT**")
    st.button("Chapter Preview", on_click=set_page, args=("Chapter Preview",), use_container_width=True)
    
    st.write("---")
    if st.button("Force Save JSON", use_container_width=True):
        memory.save()
        st.success("Saved!")
    st.caption("v0.2.3-unified | Ollama Llama 3.1")

# ----------------- Router -----------------
active_page = st.session_state.nl_nav

if active_page == "Narrative Workshop":
    render_workshop_page(memory, workflow)

elif active_page == "Project Structure":
    render_project_structure(memory)

elif active_page == "Timeline":
    render_timeline_page(memory)

elif active_page == "Characters":
    render_characters_page(memory)

elif active_page == "Relationships":
    render_relationships_page(memory)

elif active_page == "Background Settings":
    render_background_settings_page(memory)

elif active_page == "Chapter Preview":
    render_chapter_preview(memory)

else:
    st.title(active_page)
    st.info("Module under development.")
