import streamlit as st
from src.core.persistence import ProjectMemory

def render(memory: ProjectMemory):
    st.header("Characters")
    st.caption("Confirm generated candidates or manage active roster.")

    chars = memory.data.get("characters", [])
    candidates = [c for c in chars if c.get("status") == "candidate"]
    active = [c for c in chars if c.get("status") == "active"]

    # 1. Candidates Section
    if candidates:
        st.subheader("New Candidates")
        st.info("These characters were proposed by AI. Confirm them to use in generation.")
        for can in candidates:
            with st.container():
                c1, c2, c3 = st.columns([4, 1, 1])
                c1.markdown(f"**{can['name']}** - {can.get('traits', 'No traits listed')}")
                if c2.button("Confirm", key=f"conf_{can['id']}", use_container_width=True):
                    memory.confirm_character(can['id'])
                    st.rerun()
                if c3.button("Reject", key=f"rej_{can['id']}", use_container_width=True):
                    memory.delete_character(can['id'])
                    st.rerun()
        st.write("---")

    # 2. Active Roster
    col_list, col_details = st.columns([1, 2])
    
    with col_list:
        st.subheader("Active Roster")
        if not active:
            st.info("No active characters.")
        else:
            for char in active:
                if st.button(char["name"], key=f"act_{char['id']}", use_container_width=True):
                    st.session_state.nl_selected_char_id = char['id']
        
        if st.button("+ Manual Add"):
            st.session_state.nl_selected_char_id = "NEW"

    with col_details:
        sel_id = st.session_state.get("nl_selected_char_id")
        if sel_id == "NEW":
            with st.form("manual_char"):
                name = st.text_input("Name")
                desc = st.text_area("Description")
                if st.form_submit_button("Save"):
                    new_c = memory.add_character(name, desc, "", "", "")
                    memory.confirm_character(new_c['id'])
                    st.rerun()
        elif sel_id:
            char = next((c for c in active if c['id'] == sel_id), None)
            if char:
                st.subheader(char["name"])
                char["description"] = st.text_area("Background", value=char.get("description", ""))
                char["traits"] = st.text_input("Traits", value=str(char.get("traits", "")))
                char["goals"] = st.text_input("Goals", value=str(char.get("goals", "")))
                char["secrets"] = st.text_area("Secrets", value=str(char.get("secrets", "")))
                if st.button("Save Changes"):
                    memory.save()
                    st.success("Updated")
                if st.button("Move back to Candidates"):
                    char["status"] = "candidate"
                    memory.save()
                    st.rerun()
