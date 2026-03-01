import streamlit as st
import json
from src.core.persistence import ProjectMemory
from src.ai.workflow import NarrativeWorkflow

STAGES = ["IDEA_INPUT", "CLARIFIER_DECISION", "CLARIFIER_QA", "POST_CLARIFIER_DECISION", "GENERATING", "RESULT"]

def render_workshop_page(memory: ProjectMemory, workflow: NarrativeWorkflow):
    st.header("Narrative Workshop")
    st.caption("Unified pipeline: Idea -> Clarify -> Build.")

    if "nl_stage" not in st.session_state:
        st.session_state.nl_stage = "IDEA_INPUT"
    
    stage = st.session_state.nl_stage

    # 1. Idea Input
    if stage == "IDEA_INPUT":
        st.subheader("What is on your mind?")
        idea = st.text_area("Initial Idea / Prompt", placeholder="e.g. I want to write a conflict between Lorian and the Glass Guild...")
        if st.button("Continue"):
            if idea:
                st.session_state.nl_current_idea = idea
                st.session_state.nl_stage = "CLARIFIER_DECISION"
                st.rerun()

    # 2. Decision: Clarify or Skip
    elif stage == "CLARIFIER_DECISION":
        st.subheader("Clarification")
        st.write(f"**Idea:** {st.session_state.nl_current_idea}")
        c1, c2 = st.columns(2)
        if c1.button("Use Clarifier (10 Questions)", use_container_width=True):
            with st.spinner("Generating questions..."):
                questions = workflow.generate_clarification_questions(st.session_state.nl_current_idea, memory.data["canon_facts"])
                st.session_state.nl_questions = questions
                st.session_state.nl_answers = ["" for _ in questions]
                st.session_state.nl_skips = [False for _ in questions]
                st.session_state.nl_stage = "CLARIFIER_QA"
                st.rerun()
        if c2.button("Skip & Generate Direct", use_container_width=True):
            st.session_state.nl_qa_results = []
            st.session_state.nl_stage = "GENERATING"
            st.rerun()

    # 3. Clarifier Q&A
    elif stage == "CLARIFIER_QA":
        st.subheader("Research Interview")
        questions = st.session_state.nl_questions
        
        for i, q in enumerate(questions):
            col_q, col_a, col_s = st.columns([3, 4, 1])
            col_q.write(f"Q{i+1}: {q}")
            st.session_state.nl_answers[i] = col_a.text_input(f"Answer {i+1}", key=f"ans_{i}", label_visibility="collapsed")
            st.session_state.nl_skips[i] = col_s.checkbox("Skip", key=f"skip_{i}")
        
        if st.button("Submit Answers"):
            results = []
            for i, q in enumerate(questions):
                results.append({"q": q, "a": st.session_state.nl_answers[i], "skipped": st.session_state.nl_skips[i]})
            st.session_state.nl_qa_results = results
            st.session_state.nl_stage = "POST_CLARIFIER_DECISION"
            st.rerun()

    # 4. Post-Clarifier Decision
    elif stage == "POST_CLARIFIER_DECISION":
        st.subheader("Ready to Build?")
        c1, c2 = st.columns(2)
        if c1.button("Generate Now", use_container_width=True):
            st.session_state.nl_stage = "GENERATING"
            st.rerun()
        if c2.button("Another Round (Optional)", use_container_width=True):
            # For simplicity, we just loop back or handle 2nd round logic here
            st.warning("Max 2 rounds limit. Returning to generation.")
            st.session_state.nl_stage = "GENERATING"
            st.rerun()

    # 5. Generating (Execution)
    elif stage == "GENERATING":
        st.subheader("AI Narrative Scientist at work...")
        with st.spinner("Step 1: Packaging requirements..."):
            spec = workflow.run_packager(st.session_state.nl_current_idea, st.session_state.nl_qa_results)
            st.session_state.nl_spec = spec
        
        with st.spinner("Step 2: Executing narrative generation..."):
            # Snapshot of memory (limited for context window)
            snapshot = {
                "facts": memory.data["canon_facts"][:10],
                "characters": memory.data["characters"],
                "events": memory.data["timeline_events"]
            }
            result = workflow.run_core_agent(spec, snapshot)
            st.session_state.nl_agent_result = result
            
        with st.spinner("Step 3: Applying updates..."):
            stats = memory.apply_project_updates(result["project_updates"])
            st.session_state.nl_update_stats = stats
            
        st.session_state.nl_stage = "RESULT"
        st.rerun()

    # 6. Result
    elif stage == "RESULT":
        res = st.session_state.nl_agent_result
        st.success("Generation Complete!")
        
        st.title(res["user_output"]["title"])
        st.markdown(res["user_output"]["content_markdown"])
        
        st.write("---")
        st.subheader("Project Updates Applied")
        stats = st.session_state.nl_update_stats
        st.write(f"鉁 Upserted: {stats['upserted']} entities")
        st.write(f"馃🗑锔 Deleted: {stats['deleted']} entities")
        
        with st.expander("View Raw Update JSON"):
            st.json(res["project_updates"])
            
        if st.button("Start New Workshop"):
            st.session_state.nl_stage = "IDEA_INPUT"
            st.rerun()
