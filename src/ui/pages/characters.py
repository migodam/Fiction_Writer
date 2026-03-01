import streamlit as st
from src.core.persistence import ProjectMemory

def render_characters_page(memory: ProjectMemory):
    st.header("Characters")
    st.caption("Manage your cast of characters.")

    characters = memory.data.get("characters", [])
    
    col_list, col_form = st.columns([1, 2])

    with col_list:
        st.subheader("Roster")
        if not characters:
            st.info("No characters added yet.")
        else:
            for char in characters:
                if st.button(char["name"], key=f"char_{char['id']}", use_container_width=True):
                    st.session_state.nl_selected_character = char['id']
                    
        st.write("---")
        if st.button("+ Add New Character", use_container_width=True):
            st.session_state.nl_selected_character = "NEW"

    with col_form:
        active_id = st.session_state.get("nl_selected_character")
        
        if active_id == "NEW":
            st.subheader("Create New Character")
            with st.form("new_char_form"):
                name = st.text_input("Name")
                desc = st.text_area("Description / Background")
                traits = st.text_input("Personality Traits")
                goals = st.text_input("Goals / Motivations")
                secrets = st.text_area("Secrets / Fears")
                if st.form_submit_button("Save Character"):
                    if name:
                        new_char = memory.add_character(name, desc, traits, goals, secrets)
                        st.session_state.nl_selected_character = new_char['id']
                        st.rerun()
                    else:
                        st.error("Name is required.")
        
        elif active_id:
            active_char = next((c for c in characters if c['id'] == active_id), None)
            if active_char:
                st.subheader(f"Edit: {active_char['name']}")
                with st.form(f"edit_char_{active_id}"):
                    name = st.text_input("Name", value=active_char["name"])
                    desc = st.text_area("Description / Background", value=active_char["description"])
                    traits = st.text_input("Personality Traits", value=active_char["traits"])
                    goals = st.text_input("Goals / Motivations", value=active_char["goals"])
                    secrets = st.text_area("Secrets / Fears", value=active_char["secrets"])
                    
                    c1, c2 = st.columns(2)
                    if c1.form_submit_button("Update Character"):
                        memory.update_character(active_id, {
                            "name": name, "description": desc, 
                            "traits": traits, "goals": goals, "secrets": secrets
                        })
                        st.success("Updated.")
                        st.rerun()
                if st.button("Delete Character", type="secondary", key=f"del_char_{active_id}"):
                    memory.delete_character(active_id)
                    st.session_state.nl_selected_character = None
                    st.rerun()
        else:
            st.info("Select a character or create a new one.")
