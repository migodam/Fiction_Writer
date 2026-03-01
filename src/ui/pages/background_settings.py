import streamlit as st
from src.core.persistence import ProjectMemory

SETTING_CATEGORIES = [
    "faction", "religion", "artifact", "place", "organization", "custom"
]

def render_background_settings_page(memory: ProjectMemory):
    st.header("Background Settings")
    st.caption("Deep dive into the lore, systems, and organizations of your universe.")

    pages = memory.data.get("setting_pages", [])
    
    col_list, col_content = st.columns([1, 2])

    with col_list:
        st.subheader("Pages")
        if not pages:
            st.info("No pages yet.")
        else:
            for page in pages:
                if st.button(f"[{page['category'].upper()}] {page['title']}", key=f"nav_{page['id']}", use_container_width=True):
                    st.session_state.nl_selected_setting_page = page['id']

        st.write("---")
        with st.expander("Add New Page"):
            new_title = st.text_input("Page Title", key="new_page_title")
            new_cat = st.selectbox("Category", SETTING_CATEGORIES)
            if st.button("Create"):
                if new_title:
                    new_page = memory.create_setting_page(new_title, new_cat)
                    st.session_state.nl_selected_setting_page = new_page['id']
                    st.rerun()

    with col_content:
        active_id = st.session_state.get("nl_selected_setting_page")
        active_page = next((p for p in pages if p['id'] == active_id), None)

        if active_page:
            st.subheader(active_page['title'])
            st.caption(f"Category: {active_page['category']}")
            
            content = st.text_area("Content (Markdown)", value=active_page['content_markdown'], height=400)
            
            c1, c2 = st.columns(2)
            if c1.button("Save Changes", key=f"save_{active_id}"):
                memory.update_setting_page(active_id, {"content_markdown": content})
                st.success("Page updated.")
            if c2.button("Delete Page", type="secondary", key=f"del_{active_id}"):
                memory.delete_setting_page(active_id)
                st.session_state.nl_selected_setting_page = None
                st.rerun()
            
            st.write("---")
            st.markdown(content)
        else:
            st.info("Select a page from the left to view or edit.")
