import streamlit as st
import uuid
from src.core.persistence import ProjectMemory

def render(memory: ProjectMemory):
    st.header("Background Settings")
    st.caption("Notebook-style lore management with dynamic fields.")

    pages = memory.data.get("setting_pages", [])
    
    col_nav, col_items, col_editor = st.columns([1, 1, 2])

    # 1. Page Navigation (Notebooks as types)
    with col_nav:
        st.subheader("Types")
        for p in pages:
            if st.button(p["title"], key=f"pg_btn_{p['id']}", use_container_width=True):
                st.session_state.nl_active_page_id = p["id"]
                st.session_state.nl_active_item_id = None
        
        st.write("---")
        with st.expander("New Type"):
            new_t = st.text_input("Title (e.g. Religions)")
            if st.button("Create Type"):
                if new_t:
                    memory.create_setting_page(new_t, "custom")
                    st.rerun()

    # 2. Item Navigation (Objects)
    active_page_id = st.session_state.get("nl_active_page_id")
    active_page = next((p for p in pages if p["id"] == active_page_id), None)
    
    with col_items:
        st.subheader("Objects")
        if active_page:
            for it in active_page.get("items", []):
                if st.button(it["name"], key=f"it_btn_{it['id']}", use_container_width=True):
                    st.session_state.nl_active_item_id = it["id"]
            
            st.write("---")
            if st.button("+ Add Object"):
                new_item = {
                    "id": str(uuid.uuid4()), "name": "New Object", "content": "", 
                    "fields": {}, "tags": [], "page_id": active_page_id
                }
                active_page["items"].append(new_item)
                memory.save()
                st.session_state.nl_active_item_id = new_item["id"]
                st.rerun()
        else:
            st.info("Select a type.")

    # 3. Item Editor
    with col_editor:
        st.subheader("Editor")
        active_item_id = st.session_state.get("nl_active_item_id")
        if active_page and active_item_id:
            item = next((it for it in active_page["items"] if it["id"] == active_item_id), None)
            if item:
                item["name"] = st.text_input("Name", value=item["name"])
                item["content"] = st.text_area("Description", value=item["content"], height=200)
                
                st.write("**Dynamic Schema (Fields)**")
                fields = item.get("fields", {})
                new_fields = {}
                # Handle existing fields
                for k, v in fields.items():
                    c1, c2, c3 = st.columns([2, 3, 1])
                    fk = c1.text_input("Key", value=k, key=f"f_k_{k}_{item['id']}")
                    fv = c2.text_input("Value", value=v, key=f"f_v_{k}_{item['id']}")
                    if not c3.button("Delete", key=f"f_d_{k}_{item['id']}"):
                        new_fields[fk] = fv
                
                item["fields"] = new_fields
                if st.button("Add New Field"):
                    item["fields"][f"new_field_{len(fields)}"] = ""
                    st.rerun()
                
                st.write("---")
                if st.button("Save Changes"):
                    memory.save()
                    st.success("Saved")
                if st.button("Delete Object", type="secondary"):
                    active_page["items"] = [it for it in active_page["items"] if it["id"] != active_item_id]
                    memory.save()
                    st.session_state.nl_active_item_id = None
                    st.rerun()
        else:
            st.info("Select an object to edit.")
