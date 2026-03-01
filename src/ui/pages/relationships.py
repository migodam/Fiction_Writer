import streamlit as st
from src.core.persistence import ProjectMemory

def render_relationships_page(memory: ProjectMemory):
    st.header("Relationships")
    st.caption("Map the connections and conflicts between characters.")

    characters = memory.data.get("characters", [])
    if not characters:
        st.warning("You need to create Characters first.")
        return

    char_names = [c["name"] for c in characters]
    rels = memory.data.get("relationships", [])

    with st.expander("Add New Relationship", expanded=True):
        with st.form("new_rel_form"):
            col1, col2 = st.columns(2)
            char_a = col1.selectbox("Character A", char_names, key="rel_a")
            char_b = col2.selectbox("Character B", char_names, key="rel_b")
            
            rel_type = st.selectbox("Type", ["Family", "Friend", "Rival", "Enemy", "Romantic", "Mentor", "Other"])
            strength = st.slider("Strength (1-10)", 1, 10, 5)
            notes = st.text_input("Notes / Dynamics")
            
            if st.form_submit_button("Record Relationship"):
                if char_a != char_b:
                    memory.add_relationship(char_a, char_b, rel_type, str(strength), notes)
                    st.success("Relationship recorded.")
                    st.rerun()
                else:
                    st.error("A character cannot have a relationship with themselves.")

    st.write("---")
    st.subheader("Relationship Map")
    
    if not rels:
        st.info("No relationships recorded yet.")
    else:
        for rel in rels:
            with st.container():
                c1, c2, c3 = st.columns([2, 3, 1])
                c1.markdown(f"**{rel['character_a']}** & **{rel['character_b']}**")
                c2.markdown(f"[{rel['relationship_type']} - Strength: {rel['strength']}] {rel['notes']}")
                if c3.button("Delete", key=f"del_rel_{rel['id']}"):
                    memory.delete_relationship(rel['id'])
                    st.rerun()
