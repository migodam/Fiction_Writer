import streamlit as st
from src.core.persistence import ProjectMemory

def render(memory: ProjectMemory):
    st.header("Project Outline")
    st.caption("A high-level view of your narrative structure, story beats, and world canon.")

    tabs = st.tabs(["Story Outline", "Canon Facts", "Project Stats"])

    with tabs[0]:
        st.subheader("Story Beats")
        outline_nodes = memory.data.get("outline", [])
        if not outline_nodes:
            st.info("No outline nodes yet. Ask the AI to generate a chapter outline.")
        else:
            for node in outline_nodes:
                is_updated = node.get("ui_metadata", {}).get("is_new_update", False)
                title = f"✨ {node.get('title', 'Untitled')}" if is_updated else node.get('title', 'Untitled')
                
                with st.expander(title, expanded=True):
                    st.markdown(f"**Status:** `{node.get('status', 'draft')}`")
                    st.markdown(node.get("summary", "No summary provided."))
                    if is_updated:
                        memory.clear_update_flag("outline", node.get("id"))

    with tabs[1]:
        st.subheader("Canon Facts")
        st.caption("Absolute truths about your world that the AI must respect.")
        canon = memory.data.get("canon_facts", [])
        
        new_fact = st.text_input("Add new canon fact...", key="new_canon_input")
        if st.button("Add Fact"):
            if new_fact:
                memory.data["canon_facts"].append(new_fact)
                memory.save()
                st.rerun()
        
        st.write("---")
        for i, fact in enumerate(canon):
            c1, c2 = st.columns([5, 1])
            c1.write(f"{i+1}. {fact}")
            if c2.button("🗑️", key=f"del_canon_{i}"):
                memory.data["canon_facts"].pop(i)
                memory.save()
                st.rerun()

    with tabs[2]:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Characters", len(memory.data.get("characters", [])))
            st.metric("Timeline Events", len(memory.data.get("timeline_events", [])))
        with col2:
            st.metric("Setting Notebooks", len(memory.data.get("setting_pages", [])))
            st.metric("Relationships", len(memory.data.get("relationships", [])))
        
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
