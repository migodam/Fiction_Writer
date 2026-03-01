import streamlit as st
import json
from src.core.persistence import ProjectMemory
from src.ai.workflow import NarrativeWorkflow

def render(memory: ProjectMemory, workflow: NarrativeWorkflow):
    st.header("Narrative Workbench")
    
    if "nl_stage" not in st.session_state:
        st.session_state.nl_stage = "INPUT"
    
    tabs = st.tabs(["Drafting", "Clarification", "Generation", "Project Updates"])
    
    # --- Tab 1: Drafting ---
    with tabs[0]:
        is_expanded = (st.session_state.nl_stage == "INPUT")
        with st.expander("Step 1: Your Idea", expanded=is_expanded):
            idea = st.text_area("Initial Idea", value=st.session_state.get("nl_current_idea", ""), height=150)
            granularity = st.slider("Timeline Granularity", 10, 40, 20)
            
            c1, c2 = st.columns(2)
            if c1.button("Start Interview (Clarifier)", use_container_width=True):
                if idea:
                    st.session_state.nl_current_idea = idea
                    st.session_state.nl_tl_granularity = granularity
                    with st.spinner("Analyzing gaps..."):
                        qs = workflow.generate_clarification_questions(idea, memory.data["canon_facts"])
                        st.session_state.nl_questions = qs
                        st.session_state.nl_answers = ["" for _ in qs]
                        st.session_state.nl_skips = [False for _ in qs]
                        st.session_state.nl_stage = "CLARIFY"
                        st.rerun()
            
            if c2.button("Skip to Generation", use_container_width=True):
                if idea:
                    st.session_state.nl_current_idea = idea
                    st.session_state.nl_tl_granularity = granularity
                    st.session_state.nl_qa_results = []
                    st.session_state.nl_stage = "GENERATE"
                    st.rerun()

    # --- Tab 2: Clarification ---
    with tabs[1]:
        if st.session_state.get("nl_questions"):
            is_expanded_q = (st.session_state.nl_stage == "CLARIFY")
            with st.expander("Step 2: Research Interview", expanded=is_expanded_q):
                for i, q in enumerate(st.session_state.nl_questions):
                    col_q, col_a, col_s = st.columns([3, 4, 1])
                    col_q.write(f"Q{i+1}: {q}")
                    st.session_state.nl_answers[i] = col_a.text_input("Answer", key=f"wb_ans_{i}", label_visibility="collapsed")
                    st.session_state.nl_skips[i] = col_s.checkbox("Skip", key=f"wb_skip_{i}")
                
                if st.button("Complete Interview"):
                    results = []
                    for i, q in enumerate(st.session_state.nl_questions):
                        results.append({"q": q, "a": st.session_state.nl_answers[i], "skipped": st.session_state.nl_skips[i]})
                    st.session_state.nl_qa_results = results
                    st.session_state.nl_stage = "GENERATE"
                    st.rerun()
        else:
            st.info("No active interview. Start from the Drafting tab.")

    # --- Tab 3: Generation ---
    with tabs[2]:
        if st.session_state.nl_stage == "GENERATE":
            st.subheader("Executing Narrative Spec...")
            with st.spinner("Packaging requirements..."):
                spec = workflow.run_packager(st.session_state.nl_current_idea, st.session_state.nl_qa_results)
                spec["timeline_granularity"] = st.session_state.nl_tl_granularity
            
            with st.spinner("Lead Narrative Scientist generating..."):
                snapshot = {
                    "facts": memory.data["canon_facts"][:10],
                    "characters": [c for c in memory.data["characters"] if c.get("status") == "active"],
                    "timeline": memory.data["timeline_events"][-10:]
                }
                result = workflow.run_core_agent(spec, snapshot)
                st.session_state.nl_agent_result = result
                st.session_state.nl_stage = "RESULT"
                st.rerun()
        
        if st.session_state.nl_stage == "RESULT":
            res = st.session_state.nl_agent_result
            st.success("Generation Successful")
            st.title(res["user_output"]["title"])
            st.markdown(res["user_output"]["content_markdown"])

    # --- Tab 4: Updates ---
    with tabs[3]:
        if st.session_state.get("nl_agent_result"):
            res = st.session_state.nl_agent_result
            st.subheader("Proposed Project Changes")
            st.json(res["project_updates"])
            
            c1, c2 = st.columns(2)
            if c1.button("Apply Updates to Project", use_container_width=True):
                summary = memory.apply_project_updates(res["project_updates"])
                st.session_state.nl_last_summary = summary
                st.success(summary)
            
            if c2.button("Undo Last Apply", use_container_width=True):
                if memory.undo_last_apply():
                    st.warning("Project reverted to backup.")
                    st.rerun()
                else:
                    st.error("No backup found.")
        else:
            st.info("Generate content first to see updates.")
