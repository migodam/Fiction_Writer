import streamlit as st
from src.core.persistence import ProjectMemory

def render(memory: ProjectMemory):
    st.header("Project Structure")
    st.caption("A high-level view of your narrative entities.")

    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Canon Facts", len(memory.data.get("canon_facts", [])))
        st.metric("Timeline Events", len(memory.data.get("timeline_events", [])))
        
    with col2:
        st.metric("Characters", len(memory.data.get("characters", [])))
        st.metric("Relationships", len(memory.data.get("relationships", [])))
        
    with col3:
        st.metric("Setting Pages", len(memory.data.get("setting_pages", [])))
        st.metric("Chapters", len(memory.data.get("chapters", [])))

    st.write("---")
    st.subheader("Data Export")
    try:
        json_data = open(memory.file_path, "rb").read()
        st.download_button(
            label="Download Project JSON",
            data=json_data,
            file_name="narrative_lab_export.json",
            mime="application/json"
        )
    except Exception as e:
        st.error(f"Could not prepare export: {e}")
