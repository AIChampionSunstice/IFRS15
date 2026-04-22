import streamlit as st
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))

from core.auth import require_auth, update_activity
require_auth()
update_activity()

from core.session_manager import SessionManager

st.set_page_config(page_title="Preuves", layout="wide")

SessionManager.init_session()

st.markdown("""
<style>
    .evidence-card {
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 1.5rem;
        margin: 1rem 0;
    }
    .field-label {
        font-size: 0.875rem;
        color: #6b7280;
        text-transform: uppercase;
        font-weight: 600;
        margin-bottom: 0.5rem;
    }
    .field-value {
        font-size: 1.5rem;
        font-weight: 700;
        color: #1a1a1a;
        margin-bottom: 1rem;
    }
    .source-found {
        background: #d1fae5;
        border-left: 4px solid #10b981;
        padding: 1rem;
        border-radius: 6px;
        margin: 1rem 0;
        font-size: 0.95rem;
        line-height: 1.6;
    }
    .source-missing {
        background: #fee2e2;
        border-left: 4px solid #ef4444;
        padding: 1rem;
        border-radius: 6px;
        margin: 1rem 0;
        font-size: 0.875rem;
    }
    .source-partial {
        background: #fef3c7;
        border-left: 4px solid #f59e0b;
        padding: 1rem;
        border-radius: 6px;
        margin: 1rem 0;
        font-size: 0.95rem;
        line-height: 1.6;
    }
    .confidence-bar {
        display: inline-block;
        width: 150px;
        height: 10px;
        background: #e5e7eb;
        border-radius: 5px;
        overflow: hidden;
        vertical-align: middle;
        margin-left: 0.5rem;
    }
    .confidence-fill {
        height: 100%;
        transition: width 0.3s ease;
    }
    .confidence-high {
        background: #10b981;
    }
    .confidence-medium {
        background: #f59e0b;
    }
    .confidence-low {
        background: #ef4444;
    }
    .contract-card {
        background: white;
        padding: 0.75rem;
        border-radius: 0.5rem;
        border: 1px solid #e2e8f0;
        margin-bottom: 0.5rem;
        cursor: pointer;
        transition: all 0.2s;
    }
    .contract-card:hover {
        border-color: #3b82f6;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .reasoning-box {
        background: #eff6ff;
        border-left: 4px solid #3b82f6;
        padding: 1.25rem;
        border-radius: 6px;
        margin: 1.5rem 0;
        font-size: 0.95rem;
        line-height: 1.7;
    }
</style>
""", unsafe_allow_html=True)

st.title(" Preuves documentaires")
st.caption("Traçabilité des extractions IFRS15 - Sources et raisonnement IA")

st.divider()

contracts = SessionManager.get_contracts()

if not contracts:
    st.info("Aucun contrat analysé. Les preuves apparaîtront après l'analyse.")
    
    if st.button("Aller à la section Upload"):
        st.switch_page("pages/1_Upload.py")
    
    st.stop()

client_names = [c.get('Client Name', f"Contrat {i+1}") for i, c in enumerate(contracts)]
selected_client = st.selectbox(" Sélectionner un contrat", client_names, key="select_contract_preuves")
selected_index = client_names.index(selected_client)
contract = contracts[selected_index]
evidence = contract.get('evidence', {})
sources = contract.get('sources', {})

st.markdown(f"### {selected_client}")

mode = evidence.get('mode', 'unknown')
if mode == 'bedrock' or mode == 'bedrock_multi_docs':
    st.success(" Analyse AWS Bedrock - Preuves réelles")
    model_name = evidence.get('model', 'Unknown')
    st.caption(f"**Modèle:** {model_name}")
else:
    st.warning(" Mode simulé")

st.divider()

reasoning = contract.get('reasoning', '')
if reasoning:
    st.subheader(" Raisonnement de l'IA")
    st.markdown(f'<div class="reasoning-box">{reasoning}</div>', unsafe_allow_html=True)
    st.divider()


def calculate_confidence(field_value, source_text):
    if not source_text or source_text == "N/A":
        return 0, "Aucune source", "confidence-low"

    if field_value in ["N/A", "TBD", "", None]:
        return 30, "Source partielle", "confidence-low"

    vague_keywords = ["non visible", "non spécifié", "à déterminer", "pas trouvé", "introuvable"]
    if any(kw in source_text.lower() for kw in vague_keywords):
        return 40, "Source incomplète", "confidence-medium"

    if len(source_text) < 30:
        return 60, "Source limitée", "confidence-medium"

    if "'" in source_text or '"' in source_text or "→" in source_text:
        return 95, "Source précise", "confidence-high"
    
    return 80, "Source valide", "confidence-high"

ifrs_fields = [
    ("Client Name", "Nom du client"),
    ("Date signature", "Date de signature"),
    ("SaaS Start Date", "Date de début SaaS"),
    ("Durée du Contrat", "Durée du contrat"),
    ("Scope", "Périmètre / Modules"),
    ("Price Ramp-up", "Présence de ramp-up"),
    ("Ramp up price", "Type de ramp-up"),
    ("Ramp up price impact € vs TCV", "Montant ramp-up (€)"),
    ("Ramp-up price % TCV", "Pourcentage AGI"),
    ("IFRS 15 AGI", "Conformité IFRS15"),
    ("Setup fees", "Frais de setup"),
    ("Setup fees €", "Montant setup (€)"),
    ("Start date ignition", "Date de facturation"),
    ("End date théorique", "Date de fin théorique")
]

st.subheader(" Détail des champs extraits")

for field_key, field_label in ifrs_fields:
    field_value = contract.get(field_key, "N/A")
    source_text = sources.get(field_key, "") if sources else ""

    confidence_score, confidence_label, confidence_class = calculate_confidence(field_value, source_text)
    
    st.markdown(f'<div class="evidence-card">', unsafe_allow_html=True)
    st.markdown(f'<div class="field-label">{field_label}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="field-value">{field_value}</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div style="margin: 1rem 0;">
        <strong>Confiance:</strong> {confidence_score}% - {confidence_label}
        <div class="confidence-bar">
            <div class="confidence-fill {confidence_class}" style="width: {confidence_score}%"></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if source_text and source_text != "N/A":
        if confidence_score >= 70:
            st.markdown(f"""
            <div class="source-found">
                <strong> Source trouvée :</strong><br>
                {source_text}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="source-partial">
                <strong> Source incomplète :</strong><br>
                {source_text}
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="source-missing">
            <strong> Aucune source documentaire trouvée</strong><br>
            La valeur a été déduite ou calculée sans référence explicite dans le contrat.
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

st.divider()
st.subheader(" Documents analysés")

files = contract.get('files', [])
uploaded_files = evidence.get('uploaded_files', [])

if files:
    st.markdown("**Fichiers sources :**")
    for i, filename in enumerate(files, 1):
        st.markdown(f"{i}. `{filename}`")
else:
    st.caption("Aucun fichier enregistré")

if uploaded_files:
    with st.expander(" Fichiers S3 (détails techniques)"):
        for i, s3_url in enumerate(uploaded_files, 1):
            st.caption(f"{i}. {s3_url}")

st.divider()
st.subheader("Métadonnées de l'analyse")

col1, col2, col3 = st.columns(3)

with col1:
    text_len = evidence.get('text_extracted_length', 0)
    st.metric("Texte extrait", f"{text_len:,} caractères")

with col2:
    docs_count = evidence.get('total_files', len(files))
    st.metric("Documents analysés", docs_count)

with col3:
    timestamp = evidence.get('timestamp', 'N/A')
    if timestamp != 'N/A':
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(timestamp)
            timestamp = dt.strftime('%d/%m/%Y %H:%M')
        except:
            pass
    st.metric("Analysé le", timestamp)

st.divider()
st.subheader(" Qualité des preuves")

total_fields = len(ifrs_fields)
fields_with_sources = sum(1 for _, field_key in [(label, key) for key, label in ifrs_fields] 
                          if sources.get(field_key) and sources.get(field_key) != "N/A")
high_confidence = sum(1 for _, field_key in [(label, key) for key, label in ifrs_fields]
                     if calculate_confidence(contract.get(field_key), sources.get(field_key, ""))[0] >= 70)

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Champs extraits", total_fields)

with col2:
    st.metric("Avec sources", f"{fields_with_sources}/{total_fields}")
    pct_sources = (fields_with_sources / total_fields * 100) if total_fields > 0 else 0
    st.caption(f"{pct_sources:.0f}% de traçabilité")

with col3:
    st.metric("Haute confiance", f"{high_confidence}/{total_fields}")
    pct_conf = (high_confidence / total_fields * 100) if total_fields > 0 else 0
    st.caption(f"{pct_conf:.0f}% de fiabilité")

with st.expander(" Données brutes (debug)"):
    st.json(evidence)

with st.sidebar:
    st.header(" Contrats disponibles")
    
    for idx, c in enumerate(contracts):
        client = c.get('Client Name', f'Contrat {idx+1}')
        conformite = c.get('IFRS 15 AGI', 'N/A')
        date_sig = c.get('Date signature', 'N/A')
        
        if conformite == "Yes":
            badge_color = "#10b981"
            badge_text = "✓ Conforme"
        elif conformite == "No":
            badge_color = "#ef4444"
            badge_text = "✗ Non conforme"
        else:
            badge_color = "#9ca3af"
            badge_text = "N/A"
        
        border_style = "border: 2px solid #3b82f6;" if client == selected_client else ""
        
        st.markdown(f"""
        <div class="contract-card" style="{border_style}">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem;">
                <strong style="font-size: 0.875rem;">{client}</strong>
                <span style="background: {badge_color}; color: white; padding: 0.2rem 0.4rem; border-radius: 4px; font-size: 0.65rem;">{badge_text}</span>
            </div>
            <div style="font-size: 0.7rem; color: #64748b;">{date_sig}</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.divider()
    
    st.header(" Informations")
    
    st.metric("Champs tracés", len(ifrs_fields))
    st.metric("Sources disponibles", len(sources))
    
    st.divider()
    
    st.caption("""
    Concernant les indices de conrfiances
    
    - **99%+** : Source avec citation précise
    - **80%** : Source documentée
    - **60%** : Source limitée
    - **40%** : Source incomplète
    - **30%** : Source partielle
    - **0%** : Aucune source
    """)