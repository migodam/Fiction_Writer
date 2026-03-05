import streamlit as st
import json
from typing import Any, Optional
from datetime import datetime
from src.core.persistence import ProjectMemory
from src.core.memory_store import MemoryStore
from src.ai.openai_client import OpenAIClient
from src.ai.router import route_user_input
from src.ai.orchestrator import run_pipeline

def render_workbench(memory: ProjectMemory, workflow: Any = None):
    st.header("AI Workbench (Multi-Agent Engine)")
    st.caption("v0.3.0 - Orchestrated Planning & Governance")

    store = MemoryStore()

    if "nl_runs" not in st.session_state:
        st.session_state.nl_runs = []
    if "nl_wb_text" not in st.session_state:
        st.session_state.nl_wb_text = ""
    if "nl_routing" not in st.session_state:
        st.session_state.nl_routing = None

    # Top Area: Input and Routing
    user_text = st.text_area("What would you like to build or change?", value=st.session_state.nl_wb_text, height=100)
    
    col1, col2 = st.columns([1, 4])
    if col1.button("Analyze Intent"):
        if user_text:
            client = OpenAIClient(api_key=st.session_state.get("openai_api_key"), model=st.session_state.get("openai_model", "gpt-4o-mini"))
            with st.spinner("Routing..."):
                routing = route_user_input(user_text, {}, {}, client)
                st.session_state.nl_routing = routing
                st.session_state.nl_wb_text = user_text
                st.rerun()

    routing = st.session_state.nl_routing
    ui_choice = "Both" # default
    if routing:
        st.info(f"Intent: {routing.get('intent_type', 'unknown').upper()}")
        
        if routing.get("ambiguous_update"):
            st.warning("Ambiguous Target. Please clarify:")
            ui_choice = st.radio("Update target:", ["Project Updates (entities)", "Global Rules (governance)", "Both"], index=0)
        
        if st.button("Execute Pipeline", type="primary"):
            client = OpenAIClient(api_key=st.session_state.get("openai_api_key"), model=st.session_state.get("openai_model", "gpt-4o-mini"))
            with st.spinner("Orchestrating agents..."):
                res = run_pipeline(st.session_state.nl_wb_text, ui_choice, {}, memory, store, client, routing)
                
                run_record = {
                    "ts": datetime.now().isoformat(),
                    "user_text": st.session_state.nl_wb_text,
                    "routing": routing,
                    "result": res
                }
                st.session_state.nl_runs.append(run_record)
                
                # Auto-apply agent tasks for simplicity in this MVP
                agent_props = res.get("proposals", {}).get("agents", [])
                if agent_props:
                    for prop in agent_props:
                        # naive auto-apply for agent files
                        pass
                        
                st.session_state.nl_routing = None
                st.session_state.nl_wb_text = ""
                st.rerun()

    st.write("---")
    
    # Render Pending Proposals (Memory Inbox)
    if st.session_state.nl_runs:
        last_run = st.session_state.nl_runs[-1]
        global_props = last_run["result"].get("proposals", {}).get("global", [])
        if global_props:
            with st.expander("📥 Memory Inbox (Pending Global Approvals)", expanded=True):
                for i, prop in enumerate(global_props):
                    st.write(f"**Proposal:** {prop.get('file_path', 'unknown')}")
                    content = st.text_area("Proposed Content", value=prop.get('content', ''), key=f"prop_{i}")
                    c1, c2 = st.columns(2)
                    if c1.button("Approve & Save", key=f"app_{i}"):
                        store.apply_global_change_with_backup(prop.get('file_path', 'memory/global/governance.md'), content)
                        st.success("Approved!")
                    if c2.button("Reject", key=f"rej_{i}"):
                        st.info("Rejected.")

    # Render History (Append-only)
    st.subheader("Run History")
    for idx, run in enumerate(reversed(st.session_state.nl_runs)):
        res = run["result"]
        with st.expander(f"Run at {run['ts'][:19]} - {run['user_text'][:30]}...", expanded=(idx==0)):
            st.write(f"**Prompt:** {run['user_text']}")
            
            # Agent Console
            with st.container():
                st.markdown("### 🤖 Agent Console")
                
                # Context Stats
                st.caption(f"Context used: {res['context_stats'].get('used_chars', 0)} / {res['context_stats'].get('char_budget', 12000)} chars")
                if res['context_stats'].get('truncated'):
                    st.warning(res['context_stats'].get('overflow_summary', 'Context truncated.'))
                
                # Errors & Diagnostics
                diag = res.get("diagnostics", {})
                if diag.get("pipeline_error_summary"):
                    st.error(diag["pipeline_error_summary"])
                
                if res.get("errors"):
                    with st.expander("Detailed Pipeline Errors"):
                        for err in res["errors"]:
                            st.write(f"- **{err['stage']}**: {err['error']}")
                
                if diag.get("core_planner_missing_keys_a"):
                    st.warning(f"Stage A missing keys: {', '.join(diag['core_planner_missing_keys_a'])}")
                if diag.get("core_planner_missing_keys_b"):
                    st.warning(f"Stage B missing keys: {', '.join(diag['core_planner_missing_keys_b'])}")
                
                st.info(f"Expansion stage ran: {diag.get('expansion_stage_ran', False)}")

                # Raw Output
                with st.expander("View Core Planner Raw Output (Stage A)", expanded=False):
                    raw_a = diag.get("core_planner_raw_a", "")
                    st.code(raw_a if raw_a else "(empty raw, length=0)", language="json")
                    if diag.get("core_planner_err_a"):
                        st.error(f"Stage A Error: {diag['core_planner_err_a']}")

                if diag.get("expansion_stage_ran"):
                    with st.expander("View Core Planner Raw Output (Stage B)", expanded=False):
                        raw_b = diag.get("core_planner_raw_b", "")
                        st.code(raw_b if raw_b else "(empty raw, length=0)", language="json")
                        if diag.get("core_planner_err_b"):
                            st.error(f"Stage B Error: {diag['core_planner_err_b']}")

                # --- Failure Analysis ---
                if diag.get("failure_explanation"):
                    with st.expander("Why no updates? (Failure Analysis)", expanded=True):
                        st.markdown(diag["failure_explanation"])
                        if diag.get("failure_reasons"):
                            st.write("**Detected Issues:**")
                            for reason in diag["failure_reasons"]:
                                st.write(f"- {reason}")

                # Results
                st.markdown("**Core Planner Output:**")
                st.markdown(res['core_summary'].get('content_markdown', '*(No content generated)*'))
                
                if res['pm_counts']:
                    st.markdown("**Project Manager Updates Applied:**")
                    st.json(res['pm_counts'])
