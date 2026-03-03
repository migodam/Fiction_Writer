import streamlit as st
from src.core.persistence import ProjectMemory
from src.ai.workflow import NarrativeWorkflow

def render(memory: ProjectMemory):
    st.header("Characters")
    st.caption("Central hub for character development and cross-referenced history.")

    chars = memory.data.get("characters", [])
    candidates = [c for c in chars if c.get("status") == "candidate"]
    active = [c for c in chars if c.get("status") == "active"]

    # --- Pending Candidates ---
    if candidates:
        with st.expander(f"Review AI-Generated Candidates ({len(candidates)})", expanded=True):
            for can in candidates:
                c1, c2, c3 = st.columns([4, 1, 1])
                c1.write(f"**{can['name']}** - {can.get('role', 'Potential Character')}")
                if c2.button("Confirm", key=f"conf_{can['id']}"):
                    memory.confirm_character(can['id'])
                    st.rerun()
                if c3.button("Reject", key=f"rej_{can['id']}"):
                    memory.delete_character(can['id'])
                    st.rerun()

    col_nav, col_main = st.columns([1, 3])

    with col_nav:
        st.subheader("Active Roster")
        for char in active:
            if st.button(char["name"], key=f"nav_c_{char['id']}", use_container_width=True):
                st.session_state.nl_active_char_id = char["id"]
        
        if st.button("+ New Character", use_container_width=True):
            st.session_state.nl_active_char_id = "NEW"

    with col_main:
        cid = st.session_state.get("nl_active_char_id")
        if cid == "NEW":
            with st.form("manual_char_v4"):
                name = st.text_input("Name")
                role = st.text_input("Role")
                if st.form_submit_button("Create"):
                    new_c = memory.add_character(name, "", "", "", "")
                    new_c["role"] = role
                    memory.confirm_character(new_c["id"])
                    st.rerun()
        
        elif cid:
            char = next((c for c in active if c["id"] == cid), None)
            if char:
                st.title(char["name"])
                st.caption(f"Role: {char.get('role', 'N/A')}")
                
                tabs = st.tabs(["Profile", "Relationships", "Timeline Involvement", "POV Insights"])
                
                with tabs[0]:
                    char["description"] = st.text_area("Background", value=char.get("description", ""))
                    c1, c2 = st.columns(2)
                    char["traits"] = c1.text_area("Traits", value=str(char.get("traits", "")))
                    char["speech_style"] = c2.text_area("Speech Style", value=str(char.get("speech_style", "")))
                    
                    char["goals"] = st.text_area("Goals", value=str(char.get("goals", "")))
                    char["fears"] = st.text_area("Fears", value=str(char.get("fears", "")))
                    char["secrets"] = st.text_area("Secrets", value=str(char.get("secrets", "")))
                    
                    if st.button("Save Profile Updates"):
                        memory.save()
                        st.success("Profile updated.")

                with tabs[1]:
                    st.subheader("Relationships")
                    rels = memory.data.get("relationships", [])
                    # Filter: Match by ID or Name
                    char_rels = [r for r in rels if r.get("a_id") == cid or r.get("b_id") == cid or r.get("character_a") == char["name"] or r.get("character_b") == char["name"]]
                    if not char_rels:
                        st.info("No recorded connections.")
                    for r in char_rels:
                        other = r.get("character_b") if (r.get("character_a") == char["name"] or r.get("a_id") == cid) else r.get("character_a")
                        st.write(f"**With {other}:** {r.get('type')} (Strength: {r.get('strength')}/100)")
                        st.caption(f"Hidden Truth: {r.get('hidden_truth', 'Unknown')}")
                        st.write("---")

                with tabs[2]:
                    st.subheader("Timeline Involvement")
                    timeline = memory.data.get("timeline_events", [])
                    involved_events = [e for e in timeline if char["name"] in str(e.get("participants", [])) or cid in str(e.get("participants", []))]
                    if not involved_events:
                        st.info("This character has no recorded timeline events.")
                    for e in sorted(involved_events, key=lambda x: str(x.get("time"))):
                        with st.container():
                            st.markdown(f"**{e['time']} - {e['title']}**")
                            st.write(e.get("summary"))
                            st.caption(f"Location: {e.get('location')} | Consequences: {e.get('consequences')}")
                            st.write("---")

                with tabs[3]:
                    st.subheader("AI-Generated POV Analysis")
                    st.caption("Dynamic generation based on the timeline above. (Not saved to JSON)")
                    if st.button("Generate POV Insights"):
                        # Only use the involved events
                        involved_events = [e for e in memory.data.get("timeline_events", []) if char["name"] in str(e.get("participants", []))]
                        if involved_events:
                            workflow = NarrativeWorkflow(api_key=st.session_state.get("openai_api_key"), language=st.session_state.get("creative_language", "English"))
                            insights = workflow.generate_pov_timeline(char["name"], involved_events[:5]) # Limit to 5 for speed
                            for ins in insights:
                                ev = next((e for e in involved_events if e["id"] == ins["event_id"]), None)
                                title = ev["title"] if ev else "Unknown Event"
                                st.write(f"**Event: {title}**")
                                st.write(ins["perspective"])
                                st.write("---")
                        else:
                            st.warning("Need timeline events to generate insights.")
        else:
            st.info("Select a character to explore their narrative weight.")
