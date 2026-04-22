import streamlit as st
import bcrypt
from datetime import datetime, timedelta

SESSION_TIMEOUT_MINUTES = 20

def _verify(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def _get_users():
    users = {}
    try:
        for key, val in st.secrets.get("users", {}).items():
            users[val["email"]] = {
                "password": val["password_hash"],
                "name": val["name"],
                "role": val["role"]
            }
    except Exception:
        pass
    return users

def check_credentials(email: str, password: str) -> bool:
    users = _get_users()
    if email in users:
        return _verify(password, users[email]["password"])
    return False

def login(email: str):
    users = _get_users()
    st.session_state.logged_in = True
    st.session_state.user_email = email
    st.session_state.user_info = users[email]
    st.session_state.login_time = datetime.now()
    st.session_state.last_activity = datetime.now()

def logout():
    st.session_state.logged_in = False
    st.session_state.user_email = None
    st.session_state.user_info = None
    st.session_state.pop("login_time", None)
    st.session_state.pop("last_activity", None)

def is_logged_in() -> bool:
    return st.session_state.get("logged_in", False)

def check_timeout() -> bool:
    last = st.session_state.get("last_activity")
    if last and (datetime.now() - last) > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
        logout()
        return True
    return False

def update_activity():
    st.session_state.last_activity = datetime.now()

def get_remaining_minutes() -> int:
    last = st.session_state.get("last_activity")
    if not last:
        return 0
    remaining = timedelta(minutes=SESSION_TIMEOUT_MINUTES) - (datetime.now() - last)
    return max(0, int(remaining.total_seconds() / 60))

def require_auth():
    if is_logged_in():
        if check_timeout():
            st.warning("Session expirée. Reconnectez-vous.")
            st.stop()
        update_activity()
        return
    st.error("Vous devez vous connecter pour accéder à cette page.")
    st.info("Retournez à la page d'accueil pour vous connecter.")
    st.stop()