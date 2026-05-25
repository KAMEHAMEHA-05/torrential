active_sessions = {}


def get_session(session_id):

    return active_sessions.get(session_id)


def register_session(
    session_id,
    session
):

    active_sessions[session_id] = session


def remove_session(session_id):

    active_sessions.pop(
        session_id,
        None
    )