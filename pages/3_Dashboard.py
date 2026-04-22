import streamlit as st
from pathlib import Path
import sys
import pandas as pd

sys.path.append(str(Path(__file__).parent.parent))

if 'logged_in' not in st.session_state:
    from pathlib import Path as _P; import pickle as _pk, datetime as _dt
    _sf = _P(__file__).parent.parent / "data" / ".session"
    try:
        if _sf.exists():
            _d = _pk.load(open(_sf, "rb"))
            _la = _d.get("last_activity")
            if _la and (_dt.datetime.now() - _la).seconds < 1200:
                for _k, _v in _d.items(): st.session_state[_k] = _v
    except Exception: pass
if not st.session_state.get('logged_in', False):
    st.error("Vous devez vous connecter pour accéder à cette page")
    st.info("Retournez à la page d'accueil pour vous connecter")
    st.stop()

from core.session_manager import SessionManager
from core.visualizations import IFRS15Visualizer

st.set_page_config(page_title="Dashboard Analytics", layout="wide")

SessionManager.init_session()

st.title("Dashboard Analytics IFRS15")
st.caption("Vue d'ensemble et analyse détaillée de vos contrats")

contracts = SessionManager.get_contracts()

if not contracts:
    st.info("Aucune donnée disponible. Commencez par analyser des contrats.")
    if st.button("Aller à la section Upload"):
        st.switch_page("pages/1_Upload.py")
    st.stop()

metrics = IFRS15Visualizer.create_summary_metrics(contracts)
df_contracts = pd.DataFrame(contracts)

st.divider()

st.subheader("Indicateurs clés")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Contrats analysés", metrics['total_contracts'])
with col2:
    st.metric("Conformes IFRS15", metrics['compliant_contracts'])
with col3:
    st.metric("TCV Total", f"{metrics['total_tcv']:,.0f}€")
with col4:
    st.metric("Taux conformité", f"{metrics['compliance_rate']:.1f}%")

st.divider()

st.subheader("Conformité IFRS15 AGI")
fig_pie = IFRS15Visualizer.create_ifrs15_compliance_pie(contracts)
st.plotly_chart(fig_pie, use_container_width=True, key="dashboard_pie")

st.divider()

st.subheader("Tableau détaillé des contrats")

col1, col2, col3 = st.columns(3)

with col1:
    filter_compliance = st.selectbox(
        "Filtrer par conformité",
        ["Tous", "Conformes", "Non conformes"]
    )

with col2:
    if 'Client Name' in df_contracts.columns:
        sort_options = ['Client Name', 'Date signature', 'Ramp up price impact € vs TCV']
    else:
        sort_options = list(df_contracts.columns[:3])
    sort_column = st.selectbox("Trier par", sort_options)

with col3:
    if st.button("Rafraîchir"):
        st.rerun()

filtered_df = df_contracts.copy()

if filter_compliance == "Conformes":
    filtered_df = filtered_df[filtered_df['IFRS 15 AGI'] == 'Yes']
elif filter_compliance == "Non conformes":
    filtered_df = filtered_df[filtered_df['IFRS 15 AGI'] == 'No']

# Display
display_columns = [
    'Client Name', 'Type de contrat', 'Date signature',
    'Durée du Contrat', 'Ramp up price impact € vs TCV',
    'Ramp-up price % TCV', 'IFRS 15 AGI'
]
display_columns = [col for col in display_columns if col in filtered_df.columns]

st.dataframe(filtered_df[display_columns], use_container_width=True, hide_index=True)
st.caption(f"Affichage de {len(filtered_df)} contrat(s) sur {len(df_contracts)}")

st.divider()

st.subheader("Exports")

col1, col2, col3 = st.columns(3)

with col1:
    csv_data = filtered_df.to_csv(index=False)
    st.download_button(
        "Exporter CSV", csv_data, "dashboard_export.csv",
        use_container_width=True, key="export_csv_dash"
    )

with col2:
    import io
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        filtered_df.to_excel(writer, sheet_name='Contrats', index=False)
    st.download_button(
        "Exporter Excel", buffer.getvalue(), "dashboard_export.xlsx",
        use_container_width=True, key="export_excel_dash"
    )

with col3:
    json_export = SessionManager.export_session_data()
    st.download_button(
        "Exporter JSON", json_export, "session_export.json",
        use_container_width=True, key="export_json_dash"
    )

with st.sidebar:
    st.header("Contrats disponibles")
    
    for idx, contract in enumerate(contracts):
        client = contract.get('Client Name', f'Contrat {idx+1}')
        conformite = contract.get('IFRS 15 AGI', 'N/A')
        badge_color = "#10b981" if conformite == "Yes" else "#ef4444"
        badge_text = "✓" if conformite == "Yes" else "✗"
        st.markdown(f"""
        <div style="background: white; padding: 0.75rem; border-radius: 0.5rem; border: 1px solid #e2e8f0; margin-bottom: 0.5rem;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <strong style="font-size: 0.875rem;">{client}</strong>
                <span style="background: {badge_color}; color: white; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.7rem;">{badge_text}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    st.divider()
    st.header("Filtres avancés")
    st.subheader("Plage AGI (%)")
    agi_range = st.slider("AGI entre", 0.0, 100.0, (0.0, 100.0), key="agi_slider_dash")
    st.divider()
    st.caption(f"""
    **Dashboard mis à jour:**
    {pd.Timestamp.now().strftime('%d/%m/%Y %H:%M')}
    
    **Contrats affichés:** {len(filtered_df)}
    **Total session:** {len(contracts)}
    """)