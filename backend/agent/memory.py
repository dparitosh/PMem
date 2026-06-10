from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from langchain_core.chat_history import BaseChatMessageHistory
from typing import Dict, List
import os
import time

# A global in-memory session store
chat_sessions: Dict[str, List[BaseMessage]] = {}
chat_session_timestamps: Dict[str, float] = {}
CHAT_SESSION_MESSAGE_LIMIT = max(6, int(os.getenv("CHAT_SESSION_MESSAGE_LIMIT", "40")))
CHAT_SESSION_MAX_COUNT = max(10, int(os.getenv("CHAT_SESSION_MAX_COUNT", "200")))
CHAT_SESSION_TTL_SECONDS = max(300, int(os.getenv("CHAT_SESSION_TTL_SECONDS", "21600")))


def _prune_sessions() -> None:
    now = time.time()
    expired = [
        session_id
        for session_id, touched_at in chat_session_timestamps.items()
        if now - touched_at > CHAT_SESSION_TTL_SECONDS
    ]
    for session_id in expired:
        chat_sessions.pop(session_id, None)
        chat_session_timestamps.pop(session_id, None)

    if len(chat_sessions) <= CHAT_SESSION_MAX_COUNT:
        return

    overflow = len(chat_sessions) - CHAT_SESSION_MAX_COUNT
    oldest = sorted(chat_session_timestamps.items(), key=lambda item: item[1])[:overflow]
    for session_id, _ in oldest:
        chat_sessions.pop(session_id, None)
        chat_session_timestamps.pop(session_id, None)


def _touch_session(session_id: str) -> None:
    chat_session_timestamps[session_id] = time.time()
    _prune_sessions()


def _trim_messages(messages: List[BaseMessage]) -> List[BaseMessage]:
    if len(messages) <= CHAT_SESSION_MESSAGE_LIMIT:
        return messages
    return messages[-CHAT_SESSION_MESSAGE_LIMIT:]

class InMemorySessionHistory(BaseChatMessageHistory):
    def __init__(self, session_id: str):
        self.session_id = session_id
        self._load_session()

    def _load_session(self):
        _prune_sessions()
        if self.session_id not in chat_sessions:
            chat_sessions[self.session_id] = []
        _touch_session(self.session_id)
        self.messages = chat_sessions[self.session_id]

    def add_user_message(self, content: str) -> None:
        self.messages.append(HumanMessage(content=content))
        chat_sessions[self.session_id] = _trim_messages(self.messages)
        self.messages = chat_sessions[self.session_id]
        _touch_session(self.session_id)

    def add_ai_message(self, content: str) -> None:
        self.messages.append(AIMessage(content=content))
        chat_sessions[self.session_id] = _trim_messages(self.messages)
        self.messages = chat_sessions[self.session_id]
        _touch_session(self.session_id)

    def clear(self) -> None:
        chat_sessions[self.session_id] = []
        chat_session_timestamps.pop(self.session_id, None)
        self.messages = []

    def get_messages(self) -> List[BaseMessage]:
        _touch_session(self.session_id)
        return self.messages[-5:] if len(self.messages) > 5 else self.messages

def get_memory(session_id: str) -> InMemorySessionHistory:
    return InMemorySessionHistory(session_id)
