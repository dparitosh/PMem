from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from langchain_core.chat_history import BaseChatMessageHistory
from typing import Dict, List

# A global in-memory session store
chat_sessions: Dict[str, List[BaseMessage]] = {}

class InMemorySessionHistory(BaseChatMessageHistory):
    def __init__(self, session_id: str):
        self.session_id = session_id
        self._load_session()

    def _load_session(self):
        if self.session_id not in chat_sessions:
            chat_sessions[self.session_id] = []
        self.messages = chat_sessions[self.session_id]

    def add_user_message(self, content: str) -> None:
        self.messages.append(HumanMessage(content=content))

    def add_ai_message(self, content: str) -> None:
        self.messages.append(AIMessage(content=content))

    def clear(self) -> None:
        chat_sessions[self.session_id] = []
        self.messages = []

    def get_messages(self) -> List[BaseMessage]:
        return self.messages[-5:] if len(self.messages) > 5 else self.messages

def get_memory(session_id: str) -> InMemorySessionHistory:
    return InMemorySessionHistory(session_id)