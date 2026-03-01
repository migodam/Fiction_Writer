import streamlit as st
from src.core.persistence import ProjectMemory

def render_chapter_preview(memory: ProjectMemory):
    st.header("Chapter Preview")
    st.caption("Read and review your generated chapters.")

    chapters = memory.data.get("chapters", [])
    
    if not chapters:
        st.info("No chapters written yet. Use the Chapter Workshop to start writing.")
        return

    col_list, col_content = st.columns([1, 3])

    with col_list:
        st.subheader("Chapters")
        for idx, chap in enumerate(chapters):
            if st.button(f"Chapter {idx+1}: {chap.get('title', 'Untitled')}", use_container_width=True):
                st.session_state.nl_selected_chapter_id = chap.get("id")

    with col_content:
        active_id = st.session_state.get("nl_selected_chapter_id")
        active_chap = next((c for c in chapters if c.get("id") == active_id), None)
        
        if active_chap:
            st.subheader(active_chap.get("title", "Untitled"))
            st.write("---")
            st.markdown(active_chap.get("content", ""))
        else:
            st.info("Select a chapter to preview.")
