import streamlit as st
from src.core.persistence import ProjectMemory
from src.ai.openai_client import OpenAIClient

def render(memory: ProjectMemory):
    st.header("Chat Assistant")
    st.caption("Brainstorm and explore your story universe with OpenAI.")

    # LLM Config from state
    api_key = st.session_state.get("openai_api_key")
    model = st.session_state.get("openai_model", "gpt-4o-mini")

    if not api_key:
        st.warning("Please configure your OpenAI API Key in the 'App' (Workshop) page.")
        return

    # Display History
    chat_container = st.container(height=500)
    with chat_container:
        for msg in memory.data.get("chat_history", []):
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # Chat Input
    if prompt := st.chat_input("Ask the AI about your story..."):
        # User message
        with chat_container:
            st.chat_message("user").markdown(prompt)
        memory.add_assistant_chat_msg("user", prompt)
        
        # AI Response
        with chat_container:
            with st.chat_message("assistant"):
                with st.spinner(f"{model} is thinking..."):
                    try:
                        client = OpenAIClient(api_key=api_key, model=model)
                        
                        newline = "\n"
                        context = newline.join([f"- {f['content']}" for f in memory.data.get("canon_facts", [])[:10]])
                        system_prompt = f"You are a narrative assistant. Known facts:{newline}{context}"
                        
                        messages = [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ]
                        
                        ai_reply = client.chat(messages)
                        st.markdown(ai_reply)
                        memory.add_assistant_chat_msg("assistant", ai_reply, provenance=model)
                    except Exception as e:
                        st.error(f"OpenAI Error: {e}")

    if st.button("Clear Chat History", key="btn_clear_chat"):
        memory.clear_chat_history()
        st.rerun()
