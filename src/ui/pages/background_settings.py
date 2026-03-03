import streamlit as st
import uuid
from src.core.persistence import ProjectMemory

def render(memory: ProjectMemory):
    # 0. Normalization Check (One extra safety layer)
    if not isinstance(memory.data.get("setting_pages"), list):
        memory.data["setting_pages"] = []
        memory.save()

    st.header("Background Settings")
    st.caption("Notebook-style lore management. Compact 3-pane layout.")

    pages = memory.data["setting_pages"]
    
    # 1. State Keys
    PAGE_SEL_KEY = "nl_bg_selected_page_id"
    ITEM_SEL_KEY = "nl_bg_selected_item_id"

    # --- Layout: 3 Columns ---
    col_nav, col_items, col_editor = st.columns([1, 1, 2])

    # 1. Page Navigation (Notebooks)
    with col_nav:
        st.subheader("Notebooks")
        filter_p = st.text_input("Filter Pages", key="bg_filter_p", label_visibility="collapsed", placeholder="Search pages...")
        
        filtered_pages = [p for p in pages if filter_p.lower() in p.get("title", "Untitled").lower()]
        
        for i, p in enumerate(filtered_pages):
            title = p.get("title") or "Untitled"
            is_active = (st.session_state.get(PAGE_SEL_KEY) == p["id"])
            if st.button(title, key=f"pg_btn_{p['id']}_{i}", use_container_width=True, type="primary" if is_active else "secondary"):
                st.session_state[PAGE_SEL_KEY] = p["id"]
                st.session_state[ITEM_SEL_KEY] = None # Reset item on page change
                st.rerun()
        
        st.write("---")
        with st.expander("New Notebook"):
            new_title = st.text_input("Notebook Title", key="new_pg_title")
            if st.button("Create", key="btn_create_pg"):
                if new_title:
                    new_p = memory.create_setting_page(new_title)
                    st.session_state[PAGE_SEL_KEY] = new_p["id"]
                    st.rerun()

    # 2. Item Navigation (Objects)
    active_page_id = st.session_state.get(PAGE_SEL_KEY)
    active_page = next((p for p in pages if p["id"] == active_page_id), None)
    
    with col_items:
        st.subheader("Items")
        if active_page:
            filter_i = st.text_input("Filter Items", key="bg_filter_i", label_visibility="collapsed", placeholder="Search items...")
            
            filtered_items = [it for it in active_page.get("items", []) if filter_i.lower() in it.get("name", "Untitled").lower()]
            
            for it in filtered_items:
                name = it.get("name") or "Untitled"
                is_active_it = (st.session_state.get(ITEM_SEL_KEY) == it["id"])
                if st.button(name, key=f"it_btn_{it['id']}", use_container_width=True, type="primary" if is_active_it else "secondary"):
                    st.session_state[ITEM_SEL_KEY] = it["id"]
                    st.rerun()
            
            st.write("---")
            if st.button("+ New Object", use_container_width=True):
                new_it = {
                    "id": str(uuid.uuid4()), "name": "New Object", "content": "", 
                    "fields": {}, "tags": [], "page_id": active_page_id
                }
                active_page["items"].append(new_it)
                memory.save()
                st.session_state[ITEM_SEL_KEY] = new_it["id"]
                st.rerun()
            
            if st.button("Delete Notebook", type="secondary", use_container_width=True):
                memory.delete_setting_page(active_page_id)
                st.session_state[PAGE_SEL_KEY] = None
                st.rerun()
        else:
            st.info("Select a notebook.")

    # 3. Item Editor
    with col_editor:
        st.subheader("Editor")
        active_item_id = st.session_state.get(ITEM_SEL_KEY)
        if active_page and active_item_id:
            item = next((it for it in active_page["items"] if it["id"] == active_item_id), None)
            if item:
                # Top Editor
                item["name"] = st.text_input("Name", value=item.get("name", ""))
                item["content"] = st.text_area("Description / Content", value=item.get("content", ""), height=250)
                
                # Dynamic Fields
                st.write("**Fields**")
                fields = item.get("fields", {})
                new_fields = {}
                keys_to_del = []
                
                for k, v in fields.items():
                    c1, c2, c3 = st.columns([2, 3, 1])
                    fk = c1.text_input("Key", value=k, key=f"fk_{item['id']}_{k}")
                    fv = c2.text_input("Value", value=v, key=f"fv_{item['id']}_{k}")
                    if c3.button("X", key=f"fd_{item['id']}_{k}"):
                        keys_to_del.append(k)
                    else:
                        new_fields[fk] = fv
                
                item["fields"] = new_fields
                
                c_add, c_save = st.columns(2)
                if c_add.button("Add Field Row"):
                    item["fields"][f"new_field_{len(item['fields'])}"] = ""
                    st.rerun()
                
                if c_save.button("Save All Changes", type="primary", use_container_width=True):
                    memory.save()
                    st.success("JSON Persisted.")
                
                if st.button("Delete Item", type="secondary"):
                    active_page["items"] = [it for it in active_page["items"] if it["id"] != active_item_id]
                    memory.save()
                    st.session_state[ITEM_SEL_KEY] = None
                    st.rerun()
        else:
            st.info("Select an item.")
