import pytest
import os
from src.core.persistence import ProjectMemory

TEST_FILE = "data/test_memory_chat.json"

@pytest.fixture
def memory():
    if os.path.exists(TEST_FILE):
        os.remove(TEST_FILE)
    mem = ProjectMemory(file_path=TEST_FILE)
    yield mem
    if os.path.exists(TEST_FILE):
        os.remove(TEST_FILE)

def test_chat_history(memory):
    # Append
    memory.add_assistant_chat_msg("user", "Hello AI", "user_input")
    memory.add_assistant_chat_msg("assistant", "Hello Human", "llama3.1:8b")
    
    assert len(memory.data["chat_history"]) == 2
    assert memory.data["chat_history"][0]["role"] == "user"
    assert memory.data["chat_history"][1]["role"] == "assistant"
    
    # Reload
    mem2 = ProjectMemory(file_path=TEST_FILE)
    assert len(mem2.data["chat_history"]) == 2
    assert mem2.data["chat_history"][0]["content"] == "Hello AI"
    
    # Clear
    memory.clear_chat_history()
    assert len(memory.data["chat_history"]) == 0
