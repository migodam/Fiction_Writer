import streamlit as st
from src.core.persistence import ProjectMemory

SETTING_CATEGORIES = {
    "religion": "鉁 Religions",
    "guild": "馃彑 Organizations / Guilds",
    "artifact": "馃摟 Artifacts / Items",
    "place": "馃棧锔 Locations / Regions",
    "system": "馃 Systems (Magic/Tech)",
    "custom": "馃挕 Custom"
}

def render_world_settings_page(memory: ProjectMemory):
    st.header("World / Background Settings")
    st.caption("Deep dive into the lore, systems, and organizations of your universe.")

    # Sidebar for Setting Pages (Nested Sidebar)
    pages = memory.data.get("setting_pages", [])
    
    col_list, col_content = st.columns([1, 2])

    with col_list:
        st.subheader("Pages")
        if not pages:
            st.info("No pages yet.")
        else:
            for page in pages:
                icon = SETTING_CATEGORIES.get(page['category'], "馃摉")
                if st.button(f"{icon} {page['title']}", key=f"nav_{page['id']}", use_container_width=True):
                    st.session_state.active_setting_page_id = page['id']

        st.write("---")
        with st.expander("鉂曗€嶁檪锔 Create Page"):
            new_title = st.text_input("Page Title", key="new_page_title")
            new_cat = st.selectbox("Category", list(SETTING_CATEGORIES.keys()), format_func=lambda x: SETTING_CATEGORIES[x])
            if st.button("Create"):
                if new_title:
                    new_page = memory.create_setting_page(new_title, new_cat)
                    st.session_state.active_setting_page_id = new_page['id']
                    st.rerun()

    with col_content:
        active_id = st.session_state.get("active_setting_page_id")
        active_page = next((p for p in pages if p['id'] == active_id), None)

        if active_page:
            st.subheader(active_page['title'])
            st.caption(f"Category: {SETTING_CATEGORIES[active_page['category']]}")
            
            # Editor
            content = st.text_area("Content (Markdown)", value=active_page['content_markdown'], height=400)
            
            c1, c2 = st.columns(2)
            if c1.button("Save Changes"):
                memory.update_setting_page(active_id, {"content_markdown": content})
                st.success("Page updated.")
            if c2.button("Delete Page", type="secondary"):
                memory.delete_setting_page(active_id)
                st.session_state.active_setting_page_id = None
                st.rerun()
            
            st.write("---")
            st.markdown(content)
        else:
            st.info("Select a page from the left to view or edit.")
