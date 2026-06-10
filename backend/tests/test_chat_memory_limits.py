from backend.agent import memory as memory_module


def test_chat_memory_trims_to_limit(monkeypatch):
    monkeypatch.setattr(memory_module, "CHAT_SESSION_MESSAGE_LIMIT", 6)
    memory_module.chat_sessions.clear()
    memory_module.chat_session_timestamps.clear()

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
    memory_module.chat_sessions["old-session"] = []
    memory_module.chat_session_timestamps["old-session"] = 0

    memory_module.get_memory("fresh-session")

    assert "old-session" not in memory_module.chat_sessions
    assert "fresh-session" in memory_module.chat_sessions
