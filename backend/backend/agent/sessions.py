import uuid

def get_session_id() -> str:
    return str(uuid.uuid4())