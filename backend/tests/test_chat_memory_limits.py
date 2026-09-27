from backend.agent import memory as memory_module
from langchain_core.messages import HumanMessage


def test_chat_memory_trims_to_limit(monkeypatch):
    monkeypatch.setattr(memory_module, "CHAT_SESSION_MESSAGE_LIMIT", 6)
    memory_module.chat_sessions.clear()
    memory_module.chat_session_timestamps.clear()
    monkeypatch.setattr(memory_module, "load_chat_messages", lambda *_args: [])
    monkeypatch.setattr(memory_module, "replace_chat_messages", lambda *_args: None)

    session = memory_module.get_memory("demo-session")
    for idx in range(6):
        session.add_user_message(f"user-{idx}")
        session.add_ai_message(f"ai-{idx}")

    stored = memory_module.chat_sessions["demo-session"]
    assert len(stored) == 6
    assert stored[0].content == "user-3"
    assert stored[-1].content == "ai-5"


def test_chat_memory_prunes_expired_sessions(monkeypatch):
    monkeypatch.setattr(memory_module, "CHAT_SESSION_TTL_SECONDS", 1)
    memory_module.chat_sessions.clear()
    memory_module.chat_session_timestamps.clear()
    monkeypatch.setattr(memory_module, "load_chat_messages", lambda *_args: [])
    memory_module.chat_sessions["old-session"] = []
    memory_module.chat_session_timestamps["old-session"] = 0

    memory_module.get_memory("fresh-session")

    assert "old-session" not in memory_module.chat_sessions
    assert "fresh-session" in memory_module.chat_sessions


def test_conversation_history_is_loaded_before_current_turn(monkeypatch):
    from backend.agent import chat as chat_module

    class History:
        def get_messages(self):
            return [HumanMessage(content="earlier question")]

    monkeypatch.setattr(chat_module, "get_memory", lambda _session_id: History())
    messages = chat_module._conversation_messages("session-1", "current question")

    assert [message.content for message in messages] == ["earlier question", "current question"]
