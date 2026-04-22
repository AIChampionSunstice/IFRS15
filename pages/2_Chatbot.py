import streamlit as st
from pathlib import Path
import sys
import pandas as pd
from datetime import datetime
import json
import base64
import io

sys.path.append(str(Path(__file__).parent.parent))

from core.auth import require_auth, update_activity
require_auth()
update_activity()

from core.session_manager import SessionManager

st.set_page_config(page_title="Assistant IA", layout="wide")
SessionManager.init_session()

def extract_file_content(uploaded_file) -> dict:
    filename = uploaded_file.name
    ext = Path(filename).suffix.lower()
    raw_bytes = uploaded_file.getvalue()

    if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        media_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        media_type = media_map.get(ext, "image/png")
        b64 = base64.standard_b64encode(raw_bytes).decode("utf-8")
        return {
            "type": "image",
            "content": raw_bytes,
            "label": f"Image : {filename}",
            "for_claude": {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64,
                },
            },
        }

    if ext in (".xlsx", ".xls", ".csv"):
        try:
            if ext == ".csv":
                df = pd.read_csv(io.BytesIO(raw_bytes))
            else:
                df = pd.read_excel(io.BytesIO(raw_bytes))

            # Convertir en texte lisible par Claude
            text_repr = f"Fichier : {filename}\n"
            text_repr += f"Dimensions : {df.shape[0]} lignes × {df.shape[1]} colonnes\n"
            text_repr += f"Colonnes : {', '.join(str(c) for c in df.columns)}\n\n"
            text_repr += df.to_string(index=False, max_rows=200)

            return {
                "type": "dataframe",
                "content": df,
                "label": f"Tableau ({df.shape[0]}×{df.shape[1]}) : {filename}",
                "for_claude": {
                    "type": "text",
                    "text": f"[FICHIER JOINT : {filename}]\n\n{text_repr}",
                },
            }
        except Exception as e:
            return {
                "type": "text",
                "content": f"Erreur lecture fichier : {e}",
                "label": f"Erreur : {filename}",
                "for_claude": {
                    "type": "text",
                    "text": f"[FICHIER : {filename}] — impossible de lire le fichier : {e}",
                },
            }

    if ext == ".pdf":
        text = _extract_pdf_text_fast(raw_bytes, filename)
        return {
            "type": "text",
            "content": text,
            "label": f"PDF : {filename}",
            "for_claude": {
                "type": "text",
                "text": f"[PDF JOINT : {filename}]\n\n{text}",
            },
        }

    try:
        text = raw_bytes.decode("utf-8", errors="replace")
        return {
            "type": "text",
            "content": text,
            "label": f"Texte : {filename}",
            "for_claude": {
                "type": "text",
                "text": f"[FICHIER JOINT : {filename}]\n\n{text}",
            },
        }
    except Exception:
        return {
            "type": "text",
            "content": "(fichier binaire non lisible)",
            "label": f"Fichier : {filename}",
            "for_claude": {
                "type": "text",
                "text": f"[FICHIER : {filename}] — format non supporté.",
            },
        }


def _extract_pdf_text_fast(raw_bytes: bytes, filename: str) -> str:
    try:
        import fitz
        doc = fitz.open(stream=raw_bytes, filetype="pdf")
        text = f"Document : {filename}\nNombre de pages : {len(doc)}\n\n"
        for i, page in enumerate(doc):
            text += f"--- Page {i+1} ---\n"
            text += page.get_text()
            text += "\n"
            if len(text) > 50_000:
                text += "\n[document tronqué pour le chat]"
                break
        doc.close()
        return text
    except ImportError:
        return (
            f"[PDF : {filename}]\n\n"
            "PyMuPDF (fitz) n'est pas installé. "
            "Installez-le avec : pip install pymupdf\n"
            "Pour une extraction complète, passez par la page Upload."
        )
    except Exception as e:
        return f"[PDF : {filename}]\n\nErreur lors de l'extraction : {e}"

def generate_ai_response(
    question: str,
    contracts: list,
    attached_files: list
) -> str:
    """
    Génère une réponse IA avec Bedrock.
    Intègre les fichiers joints dans le message si présents.
    """

    contracts_summary = []
    for c in contracts:
        contracts_summary.append({
            "Client": c.get('Client Name', 'N/A'),
            "AGI %": c.get('Ramp-up price % TCV', 0),
            "Conforme": c.get('IFRS 15 AGI', 'N/A'),
            "Date": c.get('Date signature', 'N/A'),
            "TCV Impact": c.get('Ramp up price impact € vs TCV', 0),
            "Setup": c.get('Setup fees', 'N/A'),
            "Setup €": c.get('Setup fees €', 0),
            "Ramp-up": c.get('Price Ramp-up', 'N/A'),
            "Durée": c.get('Durée du Contrat', 'N/A'),
            "Scope": c.get('Scope', 'N/A'),
        })
    system_context = f"""Tu es un assistant IA expert en analyse IFRS15.

Contexte IFRS15 disponible :
- Nombre de contrats analysés : {len(contracts)}
- Données des contrats : {json.dumps(contracts_summary, indent=2, ensure_ascii=False)}

Instructions :
- Réponds de façon concise et précise.
- Utilise des chiffres exacts depuis les données.
- Formate les montants en euros avec séparateurs (ex: 120 000 €).
- Si la question porte sur un fichier joint, analyse-le directement.
- Si aucun contrat n'est analysé mais qu'un fichier est joint, réponds sur la base du fichier.
- Sois naturel et conversationnel.
- Le champ "Conforme" contient "Yes" (conforme) ou "No" (non conforme).
"""

    message_content = []

    for file_info in attached_files:
        message_content.append(file_info["for_claude"])

    message_content.append({
        "type": "text",
        "text": question,
    })

    if not attached_files:
        message_content = question

    try:
        from core.aws_services import AWSServices
        aws = AWSServices()

        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2000,
            "system": system_context,
            "messages": [
                {
                    "role": "user",
                    "content": message_content,
                }
            ],
        }

        response = aws.bedrock_client.invoke_model(
            modelId='global.anthropic.claude-opus-4-6-v1'
            body=json.dumps(request_body)
        )

        response_body = json.loads(response['body'].read())
        return response_body['content'][0]['text']

    except Exception as e:
        return f"Erreur Bedrock : {str(e)}"

st.markdown("""
<style>
    .chat-message {
        padding: 1rem;
        border-radius: 0.75rem;
        margin: 0.75rem 0;
        display: flex;
        gap: 1rem;
    }
    .user-message   { background: #eff6ff; border-left: 4px solid #3b82f6; }
    .assistant-message { background: #f9fafb; border-left: 4px solid #10b981; }
    .message-avatar {
        width: 36px; height: 36px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 1.1rem; flex-shrink: 0;
    }
    .user-avatar      { background: #3b82f6; color: white; }
    .assistant-avatar { background: #10b981; color: white; }
    .file-pill {
        display: inline-block;
        background: #e0f2fe; color: #0369a1;
        padding: 0.2rem 0.6rem; border-radius: 1rem;
        font-size: 0.75rem; margin: 0.2rem 0.2rem 0.4rem 0;
    }
    .stats-card {
        background: white; padding: 0.75rem;
        border-radius: 0.5rem; border: 1px solid #e2e8f0;
        text-align: center; margin-bottom: 0.75rem;
    }
</style>
""", unsafe_allow_html=True)

st.title("Assistant IA pour contrats IFRS15")
st.caption("Posez vos questions sur les contrats analysés ou uploadez un fichier — Powered by Claude Opus 4.7")

if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

if 'pending_files' not in st.session_state:
    st.session_state.pending_files = []

contracts = SessionManager.get_contracts()

with st.sidebar:
    st.header("Contexte")
    st.subheader("Joindre un fichier")
    st.caption("PDF, Excel, CSV ou image")

    uploaded_chat_file = st.file_uploader(
        "Choisir un fichier",
        type=["pdf", "xlsx", "xls", "csv", "png", "jpg", "jpeg", "gif", "webp", "txt", "md"],
        key="chat_file_uploader",
        label_visibility="collapsed",
    )

    if uploaded_chat_file is not None:
        file_data = extract_file_content(uploaded_chat_file)

        already_pending = any(
            f["label"] == file_data["label"]
            for f in st.session_state.pending_files
        )

        if not already_pending:
            st.session_state.pending_files.append(file_data)
            st.success(f"Fichier prêt : {file_data['label']}")

    if st.session_state.pending_files:
        st.markdown("**Fichiers joints (en attente d'envoi) :**")
        for i, f in enumerate(st.session_state.pending_files):
            col_f, col_x = st.columns([4, 1])
            with col_f:
                st.markdown(f"{f['label']}")
            with col_x:
                if st.button("✕", key=f"rm_file_{i}", help="Retirer ce fichier"):
                    st.session_state.pending_files.pop(i)
                    st.rerun()

        if st.button("Retirer tous les fichiers", use_container_width=True):
            st.session_state.pending_files = []
            st.rerun()

    st.divider()
    if contracts:
        st.subheader("Contrats analysés")
        for idx, contract in enumerate(contracts):
            client_name = contract.get('Client Name', f'Contrat {idx+1}')
            date_sig = contract.get('Date signature', 'N/A')
            conformite = contract.get('IFRS 15 AGI', 'N/A')
            badge_color = "#10b981" if conformite == "Yes" else "#ef4444" if conformite == "No" else "#9ca3af"
            badge_text = "✓ Conforme" if conformite == "Yes" else "✗ Non conforme" if conformite == "No" else "N/A"
            st.markdown(f"""
            <div class="stats-card">
                <div><strong>{client_name}</strong></div>
                <div style="font-size:0.75rem;color:#64748b;margin:0.2rem 0;">{date_sig}</div>
                <div style="background:{badge_color};color:white;padding:0.2rem 0.5rem;
                            border-radius:4px;font-size:0.7rem;display:inline-block;">
                    {badge_text}
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.divider()
        st.subheader("Statistiques")
        total = len(contracts)
        compliant = sum(1 for c in contracts if c.get('IFRS 15 AGI') == 'Yes')
        non_compliant = sum(1 for c in contracts if c.get('IFRS 15 AGI') == 'No')
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total", total)
            st.metric("✓ Conformes", compliant)
        with col2:
            st.metric("✗ Non conf.", non_compliant)
            taux = (compliant / total * 100) if total > 0 else 0
            st.metric("Taux", f"{taux:.0f}%")
    else:
        st.info("Aucun contrat analysé.\nUploadez des contrats ou posez des questions sur un fichier joint.")

    st.divider()

    if st.button("Effacer l'historique", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()

col_chat, col_suggest = st.columns([3, 1])

with col_suggest:
    st.subheader("Suggestions")
    suggestions_ifrs = [
        "Quels contrats sont non conformes ?",
        "Quel est le montant total de TCV ?",
        "Quels contrats ont un AGI > 5% ?",
        "Liste les dates de signature",
        "Quels sont les setup fees totaux ?",
        "Identifie les contrats avec ramp-up",
        "Quel est le scope de chaque contrat ?",
        "Compare les durées contractuelles",
    ]
    for suggestion in suggestions_ifrs:
        if st.button(suggestion, key=f"sug_{suggestion}", use_container_width=True):
            pending = list(st.session_state.pending_files)
            st.session_state.chat_history.append({
                'role': 'user', 'content': suggestion,
                'files': [f["label"] for f in pending],
                'timestamp': datetime.now().strftime("%H:%M"),
            })
            st.session_state.pending_files = []
            with st.spinner("Réflexion en cours..."):
                resp = generate_ai_response(suggestion, contracts, pending)
            st.session_state.chat_history.append({
                'role': 'assistant', 'content': resp,
                'files': [], 'timestamp': datetime.now().strftime("%H:%M"),
            })
            st.rerun()


with col_chat:
    chat_container = st.container(height=520)

    with chat_container:
        if not st.session_state.chat_history:
            if contracts:
                st.info(
                    f"{len(contracts)} contrat(s) disponible(s). "
                    "Posez vos questions ou joignez un fichier via la sidebar."
                )
            else:
                st.info(
                    "Aucun contrat analysé. Vous pouvez tout de même joindre un fichier "
                    "via la sidebar et poser des questions dessus."
                )
        else:
            for message in st.session_state.chat_history:
                if message['role'] == 'user':
                    file_pills = ""
                    for f_label in message.get('files', []):
                        file_pills += f'<span class="file-pill">{f_label}</span>'

                    st.markdown(f"""
                    <div class="chat-message user-message">
                        <div class="message-avatar user-avatar">👤</div>
                        <div>
                            {file_pills}
                            <div>{message['content']}</div>
                            <div style="font-size:0.7rem;color:#94a3b8;margin-top:0.4rem;">
                                {message['timestamp']}
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="chat-message assistant-message">
                        <div class="message-avatar assistant-avatar"></div>
                        <div>
                            <div>{message['content']}</div>
                            <div style="font-size:0.7rem;color:#94a3b8;margin-top:0.4rem;">
                                {message['timestamp']}
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
    if st.session_state.pending_files:
        pills_html = "".join(
            f'<span class="file-pill">{f["label"]}</span>'
            for f in st.session_state.pending_files
        )
        st.markdown(
            f'<div style="padding:0.5rem 0;">{pills_html}</div>',
            unsafe_allow_html=True,
        )
        st.caption("Ces fichiers seront envoyés avec votre prochain message.")

    user_input = st.chat_input(
        "Ecrire votre question...."
    )

    if user_input:
        pending = list(st.session_state.pending_files)
        st.session_state.chat_history.append({
            'role': 'user', 'content': user_input,
            'files': [f["label"] for f in pending],
            'timestamp': datetime.now().strftime("%H:%M"),
        })
        st.session_state.pending_files = []
        with st.spinner("Réflexion en cours..."):
            resp = generate_ai_response(user_input, contracts, pending)
        st.session_state.chat_history.append({
            'role': 'assistant', 'content': resp,
            'files': [], 'timestamp': datetime.now().strftime("%H:%M"),
        })
        st.rerun()
