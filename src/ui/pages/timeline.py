import streamlit as st
from src.core.persistence import ProjectMemory

def render(memory: ProjectMemory):
    st.header("Timeline")
    st.caption("Chronological story events. Fine-grained control.")

    events = memory.data.get("timeline_events", [])
    
    # 1. Search and Sort
    c1, c2 = st.columns([2, 1])
    search = c1.text_input("Search events...", placeholder="Title or participants...")
    sort_mode = c2.selectbox("Sort by", ["Time", "Creation Order"])

    filtered_events = events
    if search:
        filtered_events = [e for e in events if search.lower() in e["title"].lower() or search.lower() in str(e.get("participants", [])).lower()]
    
    if sort_mode == "Time":
        filtered_events = sorted(filtered_events, key=lambda x: str(x.get("time", "")))
    
    # 2. Main Layout
    col_list, col_details = st.columns([1, 2])

    with col_list:
        st.subheader("Event List")
        if not filtered_events:
            st.info("No events found.")
        else:
            for ev in filtered_events:
                with st.container():
                    # Compact Card
                    if st.button(f"{ev['time']} | {ev['title']}", key=f"tl_btn_{ev['id']}", use_container_width=True):
                        st.session_state.nl_active_tl_event = ev["id"]
                    st.caption(ev.get("summary", "")[:60] + "...")
                    st.write("---")
        
        if st.button("+ Manual Event", use_container_width=True):
            st.session_state.nl_active_tl_event = "NEW"

    with col_details:
        st.subheader("Details")
        active_id = st.session_state.get("nl_active_tl_event")
        
        if active_id == "NEW":
            with st.form("new_tl_form"):
                title = st.text_input("Title")
                time = st.text_input("Time / Era")
                summary = st.text_area("Summary")
                participants = st.text_input("Participants (comma separated)")
                if st.form_submit_button("Create"):
                    memory.add_timeline_event(title, time, participants, summary)
                    st.rerun()
        
        elif active_id:
            ev = next((e for e in events if e["id"] == active_id), None)
            if ev:
                ev["title"] = st.text_input("Title", value=ev["title"])
                ev["time"] = st.text_input("Time", value=ev["time"])
                ev["summary"] = st.text_area("Summary", value=ev["summary"], height=150)
                ev["participants"] = st.text_input("Participants", value=", ".join(ev.get("participants", [])))
                
                c1, c2 = st.columns(2)
                if c1.button("Save Changes"):
                    # Ensure participants is list
                    if isinstance(ev["participants"], str):
                        ev["participants"] = [p.strip() for p in ev["participants"].split(",") if p.strip()]
                    memory.save()
                    st.success("Saved")
                if c2.button("Delete Event", type="secondary"):
                    memory.delete_timeline_event(active_id)
                    st.session_state.nl_active_tl_event = None
                    st.rerun()
        else:
            st.info("Select an event to view details.")
