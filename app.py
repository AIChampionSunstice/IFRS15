import streamlit as st
from pathlib import Path
import sys
import bcrypt
import shutil
from datetime import datetime, timedelta

st.set_page_config(
    page_title="IFRS15 Analysis",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── Auth ────────────────────────────────────────────────────────────────────

def _verify(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def _get_users():
    users = {}
    try:
        for key, val in st.secrets.get("users", {}).items():
            users[val["email"]] = {
                "password": val["password_hash"],
                "name":     val["name"],
                "role":     val["role"]
            }
    except Exception:
        pass
    return users

def check_credentials(email: str, password: str) -> bool:
    users = _get_users()
    if email in users:
        return _verify(password, users[email]["password"])
    return False

def login_user(email: str):
    users = _get_users()
    st.session_state.logged_in    = True
    st.session_state.user_email   = email
    st.session_state.user_info    = users[email]
    st.session_state.login_time   = datetime.now()
    st.session_state.last_activity = datetime.now()

def logout_user():
    st.session_state.logged_in    = False
    st.session_state.user_email   = None
    st.session_state.user_info    = None
    st.session_state.pop("login_time",    None)
    st.session_state.pop("last_activity", None)

def is_logged_in() -> bool:
    return st.session_state.get("logged_in", False)

def check_session_timeout() -> bool:
    last = st.session_state.get("last_activity")
    if last and (datetime.now() - last) > timedelta(minutes=20):
        logout_user()
        return True
    return False

def update_activity():
    st.session_state.last_activity = datetime.now()

# ─── Session check ────────────────────────────────────────────────────────────

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if is_logged_in():
    if check_session_timeout():
        st.warning("Session expirée après 20 minutes d'inactivité. Reconnectez-vous.")
        st.rerun()
    else:
        update_activity()

# ─── Page login ───────────────────────────────────────────────────────────────

if not is_logged_in():
    st.markdown("""
    <style>
        .login-container { max-width: 400px; margin: 5rem auto; padding: 2rem; }
        .login-card { background: white; border: 1px solid #e5e7eb; border-radius: 12px;
                      padding: 2rem; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
        .login-title { text-align: center; font-size: 1.75rem; font-weight: 700;
                       color: #1a1a1a; margin-bottom: 0.5rem; }
        .login-subtitle { text-align: center; font-size: 0.95rem; color: #6b7280; margin-bottom: 2rem; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="login-container"><div class="login-card">', unsafe_allow_html=True)
    st.markdown('<div class="login-title">Connexion</div>', unsafe_allow_html=True)
    st.markdown('<div class="login-subtitle">Système d\'analyse IFRS15</div>', unsafe_allow_html=True)

    with st.form("login_form"):
        email    = st.text_input("Email", placeholder="prenom.nom@futurmaster.com")
        password = st.text_input("Mot de passe", type="password", placeholder="••••••••")
        submit   = st.form_submit_button("Se connecter", type="primary", use_container_width=True)

        if submit:
            if not email or not password:
                st.error("Veuillez remplir tous les champs")
            elif check_credentials(email, password):
                login_user(email)
                st.success("Connexion réussie !")
                st.rerun()
            else:
                st.error("Email ou mot de passe incorrect")

    st.markdown('</div></div>', unsafe_allow_html=True)
    st.markdown("""
    <div style="text-align:center;margin-top:2rem;color:#9ca3af;font-size:0.875rem;">
        <strong>Besoin d'aide ?</strong><br>Contactez: antoine.guerin@futurmaster.com
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ─── TEST : on s'arrête ici pour l'instant ────────────────────────────────────

st.write("Login OK ! Test étape 2")
st.stop()
