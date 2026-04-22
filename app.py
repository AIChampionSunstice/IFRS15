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

# ─── App principale ───────────────────────────────────────────────────────────

sys.path.append(str(Path(__file__).parent))
from core.session_manager import SessionManager
from core.visualizations import IFRS15Visualizer

SessionManager.init_session()

st.markdown("""
<style>
    .main { background-color: #fafafa; }
    .main-title { font-size: 2rem; font-weight: 600; color: #1a1a1a;
                  margin-bottom: 0.25rem; letter-spacing: -0.02em; }
    .main-subtitle { font-size: 0.95rem; color: #6b7280; margin-bottom: 2rem; }
    .metric-box { background: white; border: 1px solid #e5e7eb; padding: 1.25rem;
                  border-radius: 8px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
    .metric-label { font-size: 0.8125rem; color: #6b7280; font-weight: 500;
                    text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem; }
    .metric-value { font-size: 2rem; font-weight: 600; color: #1a1a1a; line-height: 1; }
    .info-box { background: #f9fafb; border: 1px solid #e5e7eb; padding: 1rem;
                border-radius: 6px; margin: 1rem 0; }
    .info-label { font-size: 0.75rem; color: #6b7280; text-transform: uppercase;
                  font-weight: 500; margin-bottom: 0.25rem; }
    .info-value { font-size: 1.25rem; font-weight: 600; color: #1a1a1a; }
    .divider { height: 1px; background: #e5e7eb; margin: 2rem 0; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">Analyse IFRS15</div>', unsafe_allow_html=True)
st.markdown('<div class="main-subtitle">Système d\'analyse automatisée de contrats SaaS</div>', unsafe_allow_html=True)
st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

contracts = SessionManager.get_contracts()
metrics   = IFRS15Visualizer.create_summary_metrics(contracts)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(f'<div class="metric-box"><div class="metric-label">Contrats</div><div class="metric-value">{metrics["total_contracts"]}</div></div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<div class="metric-box"><div class="metric-label">Conformes</div><div class="metric-value">{metrics["compliant_contracts"]}</div></div>', unsafe_allow_html=True)
with col3:
    st.markdown(f'<div class="metric-box"><div class="metric-label">TCV Total</div><div class="metric-value">{metrics["total_tcv"]:,.0f}€</div></div>', unsafe_allow_html=True)
with col4:
    st.markdown(f'<div class="metric-box"><div class="metric-label">Conformité</div><div class="metric-value">{metrics["compliance_rate"]:.0f}%</div></div>', unsafe_allow_html=True)

st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

if not contracts:
    st.info("Aucun contrat analysé. Commencez par la section Upload.")

# ─── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### Informations système")

    st.markdown(f'<div class="info-box"><div class="info-label">Contrats analysés</div><div class="info-value">{len(contracts)}</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="info-box"><div class="info-label">Seuil AGI</div><div class="info-value">{SessionManager.get_config("agi_threshold")}%</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="info-box"><div class="info-label">Conformité</div><div class="info-value">{metrics["compliance_rate"]:.0f}%</div></div>', unsafe_allow_html=True)

    st.divider()
    st.markdown("### Configuration")

    with st.expander("Seuil AGI", expanded=False):
        agi_threshold = st.slider(
            "Seuil de conformité IFRS15 (%)",
            min_value=0, max_value=20,
            value=int(SessionManager.get_config("agi_threshold")),
            step=1, key="agi_slider"
        )
        if st.button("Sauvegarder", key="save_agi"):
            SessionManager.update_config("agi_threshold", float(agi_threshold))
            st.success(f"Seuil AGI : {agi_threshold}%")

    with st.expander("Détection doublons", expanded=False):
        st.caption("Fusionne automatiquement les contrats avec des noms similaires")
        similarity_threshold = st.slider(
            "Seuil de similarité (%)",
            min_value=50, max_value=100,
            value=int(SessionManager.get_config("similarity_threshold") * 100),
            step=5, key="similarity_slider"
        )
        if st.button("Sauvegarder", key="save_similarity"):
            SessionManager.update_config("similarity_threshold", similarity_threshold / 100.0)
            st.success(f"Similarité : {similarity_threshold}%")

    st.divider()
    st.markdown("### Actions")

    with st.expander("Réinitialiser la DB", expanded=False):
        st.warning("**ATTENTION** : Supprimera TOUS les contrats de manière IRRÉVERSIBLE.")
        confirm_reset = st.text_input("Tapez 'RESET' pour confirmer :", key="confirm_reset_sidebar")
        if st.button("RÉINITIALISER", type="primary", use_container_width=True):
            if confirm_reset == "RESET":
                SessionManager.clear_session()
                data_dir = Path("data/contracts")
                if data_dir.exists():
                    shutil.rmtree(data_dir, ignore_errors=True)
                st.session_state.pop("analysis_results", None)
                st.session_state.pop("analysis_files",   None)
                st.success("DB réinitialisée !")
                import time; time.sleep(1)
                st.rerun()
            else:
                st.error("Tapez 'RESET' pour confirmer")

    st.divider()
    st.markdown("### Session")

    user_info = st.session_state.get("user_info", {})
    if user_info:
        last = st.session_state.get("last_activity")
        if last:
            remaining_min = max(0, int((timedelta(minutes=20) - (datetime.now() - last)).total_seconds() / 60))
            st.markdown(f"""
            **Connecté**  
            {user_info.get('name', 'N/A')}  
            <small style="color:#6b7280;">{user_info.get('role','N/A')}</small>  
            <small style="color:#9ca3af;">Expire dans {remaining_min} min</small>
            """, unsafe_allow_html=True)

        if st.button("Déconnexion", use_container_width=True):
            logout_user()
            st.rerun()