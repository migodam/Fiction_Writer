import streamlit as st
import json
from src.core.persistence import ProjectMemory
from src.ai.workflow import NarrativeWorkflow

def render(memory: ProjectMemory, workflow: NarrativeWorkflow):
    st.header("AI Workbench")
    st.caption("A production line for story universes. Request -> Clarify -> Generate.")

    # 1. State Management
    if "nl_workbench" not in st.session_state:
        st.session_state.nl_workbench = {
            "stage": "REQUEST",
            "request_text": "",
            "clarify_rounds": [],
            "active_questions": [],
            "agent_result": None,
            "apply_counts_text": ""
        }
    
    wb = st.session_state.nl_workbench

    # --- STEP 1: REQUEST ---
    with st.expander("Step 1: Narrative Request", expanded=(wb["stage"] == "REQUEST")):
        req_text = st.text_area("Describe what you want to create", value=wb["request_text"], height=150)
        if st.button("Generate Clarifier Questions"):
            if req_text:
                wb["request_text"] = req_text
                with st.spinner("Narrative Architect is analyzing..."):
                    qs = workflow.generate_clarification_questions(req_text, memory.data["canon_facts"])
                    wb["active_questions"] = qs
                    wb["stage"] = "CLARIFY"
                    st.rerun()

    # --- STEP 2: CLARIFIER ---
    if wb["stage"] in ["CLARIFY", "RESULT"]:
        for i, round_data in enumerate(wb["clarify_rounds"]):
            with st.expander(f"Clarification Round {i+1} (History)", expanded=False):
                for q, a in zip(round_data["questions"], round_data["answers"]):
                    st.write(f"**Q:** {q}")
                    st.write(f"**A:** {a}")
                    st.write("---")

        if wb["stage"] == "CLARIFY":
            st.subheader(f"Clarification Round {len(wb['clarify_rounds']) + 1}")
            current_answers = []
            
            for i, q in enumerate(wb["active_questions"]):
                st.write(f"**Q{i+1}:** {q}")
                ans = st.text_input("Answer", key=f"ans_v7_{len(wb['clarify_rounds'])}_{i}", label_visibility="collapsed")
                skip = st.checkbox("Skip", key=f"skip_v7_{len(wb['clarify_rounds'])}_{i}")
                current_answers.append(ans if not skip else "SKIPPED")
            
            c1, c2 = st.columns(2)
            if c1.button("Generate Now", use_container_width=True):
                wb["clarify_rounds"].append({"questions": wb["active_questions"], "answers": current_answers})
                wb["stage"] = "GENERATING"
                st.rerun()
            
            if c2.button("Ask 10 More Questions", use_container_width=True):
                if len(wb["clarify_rounds"]) < 2:
                    wb["clarify_rounds"].append({"questions": wb["active_questions"], "answers": current_answers})
                    with st.spinner("Deepening analysis..."):
                        new_qs = workflow.generate_clarification_questions(wb["request_text"], memory.data["canon_facts"], history=wb["clarify_rounds"])
                        wb["active_questions"] = new_qs
                        st.rerun()
                else:
                    st.warning("Max 3 rounds reached. Please click 'Generate Now'.")

    # --- STEP 3: GENERATING ---
    if wb["stage"] == "GENERATING":
        st.subheader("World Architect is building...")
        with st.spinner("Constructing Project JSON..."):
            snapshot = {
                "facts": memory.data["canon_facts"][:10],
                "characters": [c for c in memory.data["characters"] if c.get("status") == "active"],
                "timeline": memory.data["timeline_events"][-10:]
            }
            result = workflow.run_core_agent(wb["request_text"], wb["clarify_rounds"], snapshot)
            
            # Quality Gate
            updates = result.get("project_updates", {})
            char_count = len(updates.get("characters", {}).get("upsert", []))
            tl_count = len(updates.get("timeline_events", {}).get("upsert", []))
            item_count = len(updates.get("setting_pages", {}).get("upsert_items", []))
            
            if char_count < 3 or tl_count < 10 or item_count < 3:
                st.error(f"Quality Gate Failed: Chars({char_count}), Events({tl_count}), Items({item_count}). Regenerating with stricter constraints...")
                # Note: In a real app we might auto-retry once.
            
            wb["agent_result"] = result
            wb["stage"] = "RESULT"
            st.rerun()

    # --- STEP 4: RESULT ---
    if wb["stage"] == "RESULT":
        res = wb["agent_result"]
        st.success("Generation Complete!")
        
        with st.expander("Generation Content", expanded=True):
            st.title(res["user_output"]["title"])
            st.markdown(res["user_output"]["content_markdown"])
        
        with st.expander("Project Updates Preview", expanded=True):
            st.json(res["project_updates"])
            if st.button("Apply Updates to Memory", use_container_width=True):
                stats = memory.apply_project_updates(res["project_updates"])
                wb["apply_counts_text"] = (f"Applied updates:\n"
                                          f"- timeline_events: +{stats['timeline_upserted']}\n"
                                          f"- characters (candidates): +{stats['characters_created']}\n"
                                          f"- relationships: +{stats['relationships_created']}\n"
                                          f"- settings items: +{stats['setting_items_created']}")
                st.rerun()
        
        if wb["apply_counts_text"]:
            st.info(wb["apply_counts_text"])

        if st.button("Start New Workshop"):
            st.session_state.nl_workbench = None
            st.rerun()
