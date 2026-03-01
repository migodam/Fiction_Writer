import streamlit as st
import os
import sys
from pathlib import Path

# Fix path issues
root_path = Path(__file__).parent.parent.parent
if str(root_path) not in sys.path:
    sys.path.insert(0, str(root_path))

try:
    from src.ai.clarifier import CORE_SLOTS, analyze_coverage_from_memory, ClarifierAgent
    from src.core.persistence import ProjectMemory
    from src.ui.pages.chat_panel import render_chat_panel
    from src.ui.pages.timeline import render_timeline_page
    from src.ui.pages.world_settings import render_world_settings_page
except ImportError as e:
    st.error(f"Import Error: {e}")
    st.stop()

# ----------------- Configuration & Styling -----------------
st.set_page_config(page_title="Narrative Lab", page_icon="馃帠", layout="wide")

def load_css():
    css_path = os.path.join(os.path.dirname(__file__), "style.css")
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

load_css()

# ----------------- State Management -----------------
if "memory" not in st.session_state:
    st.session_state.memory = ProjectMemory()
if "agent" not in st.session_state:
    st.session_state.agent = ClarifierAgent(model="llama3.1:8b")
if "current_questions" not in st.session_state:
    st.session_state.current_questions = []

memory = st.session_state.memory

# ----------------- Sidebar Navigation -----------------
with st.sidebar:
    st.title("Narrative Lab")
    st.caption("AI-Powered Fiction Workshop")
    
    st.write("---")
    # Organized Navigation Categories
    st.markdown("**PLANNING**")
    page = st.radio("Navigation", [
        "馃摑 Project Overview", 
        "馃摉 Canon Facts", 
        "馃 Clarifier Interview",
        "馃摎 Chat Assistant"
    ], label_visibility="collapsed")

    st.write("---")
    st.markdown("**STRUCTURE**")
    struct_page = st.radio("Structure", [
        "馃搱 Timeline",
        "馃摎 World Settings",
        "馃懆 Characters",
        "馃🔗 Relationships"
    ], label_visibility="collapsed")

    st.write("---")
    st.markdown("**WRITING**")
    write_page = st.radio("Writing", [
        "馃摎 Chapter Workshop",
        "馃摓 Preview / Export"
    ], label_visibility="collapsed")
    
    st.write("---")
    if st.button("Save All Data", use_container_width=True):
        memory.save()
        st.success("JSON Saved!")
    
    st.caption("v0.2.5-stable | Ollama Llama 3.1")

# Determine which page to render (using session state to handle cross-sidebar navigation)
if "current_page" not in st.session_state:
    st.session_state.current_page = "馃摑 Project Overview"

# Update logic: If user clicks a different radio, update current_page
# Note: In Streamlit, separate radio groups act independently. 
# For this demo, we'll priority-order the groups.
active_page = page
if "Timeline" in struct_page: active_page = struct_page
if "World Settings" in struct_page: active_page = struct_page
# (This is a simplified multi-category router)

# ----------------- Routing -----------------

if "Overview" in active_page:
    st.header(f"Project: {memory.data['project_info']['name']}")
    col1, col2, col3 = st.columns(3)
    coverage = analyze_coverage_from_memory(memory.data['canon_facts'])
    total_cov = sum(coverage.values()) / len(coverage) if coverage else 0
    col1.metric("Canon Facts", len(memory.data['canon_facts']))
    col2.metric("Blueprint", f"{int(total_cov * 100)}%")
    col3.metric("Chapters", len(memory.data['chapters']))
    st.subheader("Narrative Coverage")
    for slot_key, slot_info in CORE_SLOTS.items():
        st.write(f"**{slot_info['label']}**")
        st.progress(coverage.get(slot_key, 0.0))

elif "Canon" in active_page:
    st.header("Canon Database")
    # (Existing Canon display logic moved here or simplified)
    facts = sorted(memory.data['canon_facts'], key=lambda x: x['timestamp'], reverse=True)
    for fact in facts:
        st.markdown(f"**[{fact['category'].upper()}]** {fact['content']}")

elif "Clarifier" in active_page:
    # Existing Clarifier logic
    st.header("Clarifier Loop")
    # ... (rest of clarifier code)
    st.info("Module active. Generate questions to fill gaps.")

elif "Chat" in active_page:
    render_chat_panel(memory)

elif "Timeline" in active_page:
    render_timeline_page(memory)

elif "World Settings" in active_page:
    render_world_settings_page(memory)

else:
    st.title(active_page)
    st.info("This module is under development.")
