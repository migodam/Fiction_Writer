import streamlit as st
import ollama
from src.core.persistence import ProjectMemory

def render_chat_panel(memory: ProjectMemory):
    st.header("Chat with Narrative AI")
    st.caption("Brainstorm, refine, and explore your story universe.")

    # Container for messages
    chat_container = st.container(height=500)
    
    with chat_container:
        for msg in memory.data["clarifier_history"]:
            role = msg["role"]
            content = msg["content"]
            with st.chat_message(role):
                st.markdown(content)

    # Chat Input
    if prompt := st.chat_input("Ask about your story..."):
        # Display user message
        with chat_container:
            st.chat_message("user").markdown(prompt)
        
        # Save to memory
        memory.add_chat_msg("user", prompt)
        
        # Call AI (non-streaming for stability in this version)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    # Provide full context (basic version)
                    facts_context = "\n".join([f"- {f['content']}" for f in memory.data["canon_facts"][:10]])
                    system_prompt = f"You are Narrative Lab AI. Assist the author. Known facts:\n{facts_context}"
                    
                    response = ollama.chat(model="llama3.1:8b", messages=[
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': prompt},
                    ])
                    full_response = response['message']['content']
                    st.markdown(full_response)
                    memory.add_chat_msg("assistant", full_response, provenance="ai_chat")
                except Exception as e:
                    st.error(f"Ollama Error: {e}")

    if st.button("Clear History"):
        memory.data["clarifier_history"] = []
        memory.save()
        st.rerun()
