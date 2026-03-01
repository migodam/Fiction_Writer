import streamlit as st
from src.core.persistence import ProjectMemory

def render_timeline_page(memory: ProjectMemory):
    st.header("Timeline Editor")
    st.caption("Map the chronological events of your story.")

    # List Existing Events
    events = memory.data.get("timeline_events", [])
    
    # Simple table-like view
    if not events:
        st.info("No events recorded yet. Add your first event below!")
    else:
        for event in sorted(events, key=lambda x: x.get("time", "")):
            with st.container():
                cols = st.columns([1, 4, 1])
                cols[0].markdown(f"**{event['time']}**")
                cols[1].markdown(f"**{event['title']}**\n\n{event['summary']}")
                if cols[2].button("Delete", key=f"del_{event['id']}"):
                    memory.delete_timeline_event(event['id'])
                    st.rerun()
                st.write("---")

    # Add Event Form
    with st.expander("Add New Event"):
        with st.form("new_event_form"):
            title = st.text_input("Event Title")
            time = st.text_input("Time / Era (e.g., Year 182)")
            participants = st.text_input("Participants (comma separated)")
            summary = st.text_area("Summary / Description")
            
            if st.form_submit_button("Create Event"):
                if title:
                    memory.add_timeline_event(title, time, participants, summary)
                    st.success("Event added to timeline.")
                    st.rerun()
                else:
                    st.error("Title is required.")
