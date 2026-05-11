import streamlit as st
from pathlib import Path
import sys
import pandas as pd

sys.path.append(str(Path(__file__).parent.parent))

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
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

# ─── KPIs principaux ──────────────────────────────────────────────────────────

st.subheader("Indicateurs clés")

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("Contrats analysés", metrics['total_contracts'])
with col2:
    st.metric("Conformes IFRS15", metrics['compliant_contracts'])
with col3:
    # TCV théorique total = somme des TCV théoriques de tous les contrats
    tcv_theorique_total = sum(
        float(c.get("TCV théorique", 0) or 0) for c in contracts
    )
    if tcv_theorique_total > 0:
        st.metric("TCV Théorique Total", f"{tcv_theorique_total:,.0f}€")
    else:
        st.metric("TCV Total", f"{metrics['total_tcv']:,.0f}€")
with col4:
    tcv_reel_total = sum(float(c.get("TCV réel", 0) or 0) for c in contracts)
    if tcv_reel_total > 0:
        st.metric("TCV Réel Total", f"{tcv_reel_total:,.0f}€")
    else:
        st.metric("Taux conformité", f"{metrics['compliance_rate']:.1f}%")
with col5:
    st.metric("Taux conformité", f"{metrics['compliance_rate']:.1f}%")

st.divider()

# ─── Graphique conformité ─────────────────────────────────────────────────────

st.subheader("Conformité IFRS15 AGI")
fig_pie = IFRS15Visualizer.create_ifrs15_compliance_pie(contracts)
st.plotly_chart(fig_pie, use_container_width=True, key="dashboard_pie")

st.divider()

# ─── Tableau détaillé ─────────────────────────────────────────────────────────

st.subheader("Tableau détaillé des contrats")

col1, col2, col3 = st.columns(3)

with col1:
    filter_compliance = st.selectbox(
        "Filtrer par conformité",
        ["Tous", "Conformes", "Non conformes"]
    )
with col2:
    sort_options = ['Client Name', 'Date signature', 'TCV théorique', 'TCV réel',
                    'ARR prix plein', 'Ramp up price impact € vs TCV']
    sort_options = [c for c in sort_options if c in df_contracts.columns]
    if not sort_options:
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

if sort_column in filtered_df.columns:
    try:
        filtered_df = filtered_df.sort_values(sort_column, ascending=False)
    except Exception:
        pass

# ─── Vue standard ─────────────────────────────────────────────────────────────

tab1, tab2 = st.tabs(["Vue standard", "Vue financière ARR / TCV"])

with tab1:
    display_columns_standard = [
        'Client Name', 'Type de contrat', 'Scope', 'Date signature',
        'Durée du Contrat', 'Price Ramp-up', 'Ramp up price',
        'Ramp up price impact € vs TCV', 'Ramp-up price % TCV', 'IFRS 15 AGI'
    ]
    display_columns_standard = [c for c in display_columns_standard if c in filtered_df.columns]
    st.dataframe(filtered_df[display_columns_standard], use_container_width=True, hide_index=True)

with tab2:
    st.markdown("""
    <style>
    .financial-info {
        background: #eff6ff; border-left: 4px solid #3b82f6;
        padding: 0.75rem 1rem; border-radius: 4px; margin-bottom: 1rem;
        font-size: 0.875rem; color: #1e40af;
    }
    </style>
    <div class="financial-info">
        <strong>Définitions IFRS 15 :</strong><br>
        • <strong>MRR standard</strong> : Loyer mensuel au prix plein (sans remise)<br>
        • <strong>ARR prix plein</strong> : MRR standard × 12 — revenu annuel récurrent théorique<br>
        • <strong>TCV théorique</strong> : MRR standard × durée totale — ce qui aurait dû être facturé sans ramp-up<br>
        • <strong>TCV réel</strong> : TCV théorique − écart ramp-up — ce qui est réellement facturé<br>
        • <strong>Écart TCV</strong> = TCV théorique − TCV réel = Ramp up price impact
    </div>
    """, unsafe_allow_html=True)

    display_columns_financial = [
        'Client Name', 'Durée du Contrat', 'Scope',
        'MRR standard', 'ARR prix plein',
        'TCV théorique', 'TCV réel',
        'Ramp up price impact € vs TCV', 'Ramp-up price % TCV',
        'IFRS 15 AGI'
    ]
    display_columns_financial = [c for c in display_columns_financial if c in filtered_df.columns]

    # Formatage des colonnes monétaires
    df_display = filtered_df[display_columns_financial].copy()
    money_cols = ['MRR standard', 'ARR prix plein', 'TCV théorique', 'TCV réel',
                  'Ramp up price impact € vs TCV']
    
    format_dict = {}
    for col in money_cols:
        if col in df_display.columns:
            format_dict[col] = "{:,.0f} €"
    if 'Ramp-up price % TCV' in df_display.columns:
        format_dict['Ramp-up price % TCV'] = "{:.1f}%"

    st.dataframe(
        df_display.style.format(format_dict, na_rep="N/A"),
        use_container_width=True,
        hide_index=True
    )

    # Totaux récapitulatifs
    if len(filtered_df) > 0:
        st.markdown("---")
        st.markdown("**Totaux**")
        recap_cols = st.columns(4)
        
        total_arr = sum(float(c.get("ARR prix plein", 0) or 0)
                        for c in contracts
                        if c.get("Client Name") in filtered_df["Client Name"].values)
        total_tcv_th = sum(float(c.get("TCV théorique", 0) or 0)
                           for c in contracts
                           if c.get("Client Name") in filtered_df["Client Name"].values)
        total_tcv_reel = sum(float(c.get("TCV réel", 0) or 0)
                             for c in contracts
                             if c.get("Client Name") in filtered_df["Client Name"].values)
        total_ecart = total_tcv_th - total_tcv_reel

        with recap_cols[0]:
            st.metric("ARR prix plein total", f"{total_arr:,.0f} €")
        with recap_cols[1]:
            st.metric("TCV théorique total", f"{total_tcv_th:,.0f} €")
        with recap_cols[2]:
            st.metric("TCV réel total", f"{total_tcv_reel:,.0f} €")
        with recap_cols[3]:
            st.metric("Écart total (remises ramp-up)", f"{total_ecart:,.0f} €")

st.caption(f"Affichage de {len(filtered_df)} contrat(s) sur {len(df_contracts)}")

st.divider()

# ─── Exports ──────────────────────────────────────────────────────────────────

st.subheader("Exports")

# Colonnes complètes pour export (ordre logique pour le DAF)
export_columns_order = [
    'Client Name', 'Type de contrat', 'Contrat format Sunstice',
    'Date signature', 'Scope', 'Durée du Contrat',
    'Price Ramp-up', 'Ramp up price',
    'MRR standard', 'ARR prix plein',
    'TCV théorique', 'TCV réel',
    'Ramp up price impact € vs TCV', 'Ramp-up price % TCV',
    'IFRS 15 AGI',
    'Option Sortie avant terme du contrat',
    'SaaS Start Date', 'Start date ignition', 'End date théorique',
    'Setup fees', 'Setup fees €'
]
export_cols = [c for c in export_columns_order if c in filtered_df.columns]
# Ajouter les colonnes restantes non listées
for col in filtered_df.columns:
    if col not in export_cols and col not in ['id', 'timestamp', 'reasoning', 'sources']:
        export_cols.append(col)

df_export = filtered_df[export_cols] if export_cols else filtered_df

col1, col2, col3 = st.columns(3)

with col1:
    csv_data = df_export.to_csv(index=False)
    st.download_button(
        "Exporter CSV", csv_data, "dashboard_export.csv",
        use_container_width=True, key="export_csv_dash"
    )
with col2:
    import io
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_export.to_excel(writer, sheet_name='Contrats', index=False)
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

# ─── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Contrats disponibles")
    
    for idx, contract in enumerate(contracts):
        client = contract.get('Client Name', f'Contrat {idx+1}')
        conformite = contract.get('IFRS 15 AGI', 'N/A')
        badge_color = "#10b981" if conformite == "Yes" else "#ef4444"
        badge_text = "✓" if conformite == "Yes" else "✗"
        arr = contract.get('ARR prix plein', 0)
        arr_str = f"{float(arr):,.0f} €" if arr and arr != 0 else "N/A"
        st.markdown(f"""
        <div style="background: white; padding: 0.75rem; border-radius: 0.5rem;
                    border: 1px solid #e2e8f0; margin-bottom: 0.5rem;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <strong style="font-size: 0.875rem;">{client}</strong>
                <span style="background: {badge_color}; color: white; padding: 0.25rem 0.5rem;
                             border-radius: 4px; font-size: 0.7rem;">{badge_text}</span>
            </div>
            <div style="font-size: 0.75rem; color: #6b7280; margin-top: 0.25rem;">
                ARR : {arr_str}
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