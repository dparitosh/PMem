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
    import ast
    import logging
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'agent' / 'chat.py'
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_conversation_messages')

    class History:
        def get_messages(self):
            return [HumanMessage(content="earlier question")]

    scope = {'get_memory': lambda _session_id: History(), 'HumanMessage': HumanMessage,
             'logger': logging.getLogger(__name__)}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec',
                 flags=__import__('__future__').annotations.compiler_flag), scope)
    messages = scope['_conversation_messages']('session-1', 'current question')

    assert [message.content for message in messages] == ["earlier question", "current question"]
