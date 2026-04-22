import streamlit as st
import pandas as pd
from pathlib import Path
import shutil
import tempfile
import sys
import io
import zipfile
import re
import contextlib
from io import StringIO

@contextlib.contextmanager
def suppress_stdout_stderr():
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    try:
        sys.stdout = StringIO()
        sys.stderr = StringIO()
        yield
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

# CSS
st.markdown("""
<style>
    .stAlert[data-baseweb="notification"] { display: none !important; }
    div[data-testid="stException"]:has(.stMarkdown) { display: none !important; }
    .element-container:has(code) { display: block !important; }
    .doc-card {
        background: white; padding: 1rem; border-radius: 0.5rem;
        border: 1px solid #e2e8f0; margin: 0.5rem 0;
    }
    .doc-type-badge { padding: 0.25rem 0.75rem; border-radius: 0.375rem; font-size: 0.75rem; font-weight: 600; }
    .type-order { background: #dbeafe; color: #1e40af; }
    .type-sow { background: #fce7f3; color: #9f1239; }
    .type-sla { background: #fef3c7; color: #92400e; }
    .type-master { background: #d1fae5; color: #065f46; }
    .type-other { background: #f3f4f6; color: #374151; }
    .aws-badge {
        background: #10b981; color: white; padding: 0.5rem 1rem;
        border-radius: 0.5rem; display: inline-block; margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

sys.path.append(str(Path(__file__).parent.parent))

from core.auth import require_auth, update_activity
require_auth()
update_activity()

from core.classify_docs import classify_document
from core.file_io import save_uploaded_file, extract_zip_to_dir, list_files_recursive
from core.session_manager import SessionManager
from core.visualizations import IFRS15Visualizer
from core.real_analyzer import analyze_contract_real
from core.client_matcher import load_client_list, group_pdfs_by_client_smart, identify_client_for_pdf, match_zip_name_to_client
from core.pdf_annotate import annotate_pdf_with_sources, merge_pdfs

st.set_page_config(page_title="Upload & Analyse", layout="wide")

SessionManager.init_session()
client_list = load_client_list()
if client_list:
    st.sidebar.success(f"{len(client_list)} clients chargés depuis clients.xlsx")
else:
    st.sidebar.warning(
        "Fichier `clients.xlsx` introuvable à la racine. "
        "Créez-le avec une colonne **Client** pour améliorer la détection automatique."
    )

if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = None
if 'analysis_files' not in st.session_state:
    st.session_state.analysis_files = None

def extract_version_number(filename: str) -> tuple:
    match = re.search(r'(?:avenant|amendment|version|v)\s*(\d+)\.(\d+)', filename, re.IGNORECASE)
    if match:
        return (int(match.group(1)), int(match.group(2)))
    match = re.search(r'(?:avenant|amendment|version|v)\s*(\d+)', filename, re.IGNORECASE)
    if match:
        return (int(match.group(1)), 0)
    match = re.search(r'_v(\d+)(?:\.(\d+))?', filename, re.IGNORECASE)
    if match:
        major = int(match.group(1))
        minor = int(match.group(2)) if match.group(2) else 0
        return (major, minor)
    return (0, 0)


def deduplicate_versions(pdf_files: list) -> list:
    groups = {}
    for pdf in pdf_files:
        filename = pdf.stem
        base_name = re.sub(r'(?:avenant|amendment|version|v)\s*\d+(?:\.\d+)?', '', filename, flags=re.IGNORECASE)
        base_name = re.sub(r'_v\d+(?:\.\d+)?', '', base_name, flags=re.IGNORECASE)
        base_name = base_name.strip('_- ')
        if base_name not in groups:
            groups[base_name] = []
        version = extract_version_number(filename)
        groups[base_name].append((pdf, version))

    result = []
    for base_name, files_with_versions in groups.items():
        if len(files_with_versions) == 1:
            result.append(files_with_versions[0][0])
        else:
            files_with_versions.sort(key=lambda x: x[1], reverse=True)
            latest = files_with_versions[0][0]
            result.append(latest)
            ignored = [f[0].name for f in files_with_versions[1:]]
            if ignored:
                st.info(f" Versions anciennes ignorées pour '{base_name}': {', '.join(ignored)}")
    return result

def extract_client_name_from_pdf(pdf_path: Path) -> str:
    try:
        import fitz
        doc = fitz.open(pdf_path)
        text = ""
        for page_num in range(min(3, len(doc))):
            text += doc[page_num].get_text()
        doc.close()
        match = re.search(r'(?:customer|client)\s*[:]\s*([A-Z][A-Za-z\s&.-]+?)(?:\n|$)', text, re.IGNORECASE)
        if match:
            client_name = match.group(1).strip()
            if len(client_name) > 3 and len(client_name) < 50:
                return client_name
        lines = text.split('\n')
        for line in lines[:30]:
            line = line.strip()
            if re.match(r'^[A-Z][A-Z\s&.-]{3,40}(?:Inc\.|Ltd\.|SA|SAS|SARL)?$', line):
                return line.strip()
        return None
    except Exception:
        return None

st.title(" Upload & Analyse de contrats")
st.caption("Importez vos documents contractuels pour une analyse automatisée IFRS15")
st.divider()

if st.session_state.analysis_results is not None:

    st.success(" Analyse terminée ! Résultats disponibles ci-dessous.")

    if st.button(" Analyser un nouveau contrat", type="primary", use_container_width=True):
        st.session_state.analysis_results = None
        st.session_state.analysis_files = None
        st.rerun()

    st.divider()

    all_results = st.session_state.analysis_results

    st.subheader(" Résultats de l'analyse")

    for client, result_row, evidence, contract_dir in all_results:

        with st.expander(f" {client}", expanded=(len(all_results) == 1)):

            agi_value = result_row.get('Ramp-up price % TCV', 0)

            col1, col2 = st.columns([1, 2])

            with col1:
                fig_gauge = IFRS15Visualizer.create_agi_gauge(agi_value, SessionManager.get_config('agi_threshold'))
                st.plotly_chart(fig_gauge, use_container_width=True, key=f"gauge_{client}")

                is_compliant = result_row.get('IFRS 15 AGI') == 'Yes'
                status_color = "#10b981" if is_compliant else "#ef4444"
                status_text = "✓ Conforme" if is_compliant else "✗ Non conforme"

                st.markdown(f"""
                <div style="background: {status_color}; color: white; padding: 1rem; border-radius: 0.5rem; text-align: center;">
                    <div style="font-size: 1.25rem; font-weight: 700;">{status_text}</div>
                    <div style="font-size: 0.875rem;">IFRS15 AGI</div>
                </div>
                """, unsafe_allow_html=True)

            with col2:
                st.markdown("####  Données extraites")
                display_row = {k: v for k, v in result_row.items()
                               if k not in ['evidence', 'sources', 'reasoning']}
                result_df = pd.DataFrame([display_row])
                st.dataframe(result_df, use_container_width=True, hide_index=True)

            if 'sources' in result_row and result_row['sources']:
                st.divider()
                st.markdown("####  Preuves extraites")
                sources = result_row['sources']
                with st.expander("Voir les preuves détaillées", expanded=False):
                    for field_name, source_text in sources.items():
                        if source_text and source_text not in ["Not found", "N/A", ""]:
                            st.markdown(f"**{field_name}**")
                            st.code(source_text, language=None)
                            st.markdown("---")

            st.divider()
            st.markdown("####  PDF annoté")

            sources = result_row.get("sources", {}) or {}
            pdf_files_raw = list(contract_dir.glob("*.pdf"))
            pdf_files = [p for p in pdf_files_raw if "ANNOTATED" not in p.name and "MERGED" not in p.name]

            if sources and pdf_files:
                annotated_path = contract_dir / f"{client}_ANNOTATED.pdf"
                try:
                    from core.pdf_annotate import annotate_pdf_with_sources, merge_pdfs
                    if not annotated_path.exists():
                        with st.spinner(" Génération du PDF annoté"):
                            with suppress_stdout_stderr():
                                if len(pdf_files) > 1:
                                    merged_path = contract_dir / f"{client}_MERGED.pdf"
                                    merge_pdfs(pdf_files, merged_path)
                                    source_pdf = str(merged_path)
                                else:
                                    source_pdf = str(pdf_files[0])

                                annotations_count, evidence_dict = annotate_pdf_with_sources(
                                    pdf_path=source_pdf,
                                    sources_dict=sources,
                                    output_path=str(annotated_path),
                                    generate_screenshots=True
                                )
                        if annotations_count > 0:
                            nb_docs = len(pdf_files)
                            label = f" {annotations_count} annotation(s) sur {nb_docs} document(s) fusionné(s)" if nb_docs > 1 else f"{annotations_count} annotation(s) ajoutée(s)"
                            st.success(label)
                        else:
                            st.warning(" Aucune annotation n'a pu être ajoutée")

                    if annotated_path.exists():
                        with open(annotated_path, "rb") as f:
                            pdf_bytes = f.read()
                        col1, col2 = st.columns([2, 1])
                        with col1:
                            st.download_button(
                                label=f" Télécharger PDF annoté - {client}",
                                data=pdf_bytes,
                                file_name=f"{client}_ANNOTATED.pdf",
                                mime="application/pdf",
                                use_container_width=True,
                                key=f"pdf_{client}"
                            )
                        with col2:
                            file_size = len(pdf_bytes) / 1024
                            st.info(f" Taille: {file_size:.1f} KB")

                except Exception as e:
                    st.error(f" Erreur PDF annoté : {str(e)}")
                    import traceback
                    with st.expander("Détails de l'erreur"):
                        st.code(traceback.format_exc())
            else:
                st.warning(" Pas de sources disponibles pour l'annotation")

            st.divider()
            st.markdown("####  Export des données")

            export_row = {k: v for k, v in result_row.items()
                          if k not in ['evidence', 'sources', 'reasoning']}
            export_df = pd.DataFrame([export_row])

            col1, col2, col3 = st.columns(3)
            with col1:
                csv_data = export_df.to_csv(index=False)
                st.download_button(" CSV", csv_data, f"ifrs15_{client}.csv",
                                   "text/csv", use_container_width=True, key=f"csv_{client}")
            with col2:
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    export_df.to_excel(writer, sheet_name='IFRS15', index=False)
                st.download_button(" Excel", buffer.getvalue(), f"ifrs15_{client}.xlsx",
                                   use_container_width=True, key=f"excel_{client}")
            with col3:
                json_data = export_df.to_json(orient='records', indent=2)
                st.download_button(" JSON", json_data, f"ifrs15_{client}.json",
                                   use_container_width=True, key=f"json_{client}")

    if len(all_results) > 1:
        st.divider()
        st.subheader(" Export consolidé")
        st.caption(f"Tous les contrats regroupés ({len(all_results)} contrats)")

        consolidated_rows = []
        for client, result_row, evidence, contract_dir in all_results:
            clean_row = {k: v for k, v in result_row.items()
                         if k not in ['evidence', 'sources', 'reasoning']}
            consolidated_rows.append({'Client': client, **clean_row})

        consolidated_df = pd.DataFrame(consolidated_rows)

        with st.expander(" Aperçu du tableau consolidé", expanded=False):
            st.dataframe(consolidated_df, use_container_width=True, hide_index=True)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.download_button(" CSV Consolidé", consolidated_df.to_csv(index=False),
                               "ifrs15_consolidated.csv", "text/csv",
                               use_container_width=True, key="csv_consolidated")
        with col2:
            buffer_consolidated = io.BytesIO()
            with pd.ExcelWriter(buffer_consolidated, engine='openpyxl') as writer:
                consolidated_df.to_excel(writer, sheet_name='Tous les contrats', index=False)
            st.download_button(" Excel Consolidé", buffer_consolidated.getvalue(),
                               "ifrs15_consolidated.xlsx",
                               use_container_width=True, key="excel_consolidated")
        with col3:
            st.download_button(" JSON Consolidé",
                               consolidated_df.to_json(orient='records', indent=2),
                               "ifrs15_consolidated.json",
                               use_container_width=True, key="json_consolidated")

    st.stop()
st.subheader("1 Import de documents")

col1, col2 = st.columns([2, 1])

with col1:
    uploaded = st.file_uploader(
        "Déposez vos fichiers ici",
        type=["pdf", "zip"],
        accept_multiple_files=False,
        help="Formats acceptés: PDF ou ZIP (peut contenir 1 ou plusieurs contrats)",
        key="file_uploader"
    )
    if uploaded:
        file_size = len(uploaded.getvalue()) / 1024
        st.success(f"Fichier chargé: **{uploaded.name}** ({file_size:.1f} KB)")

with col2:
    st.info("""
    ZIP intelligent :
    - 1 client = plusieurs docs
    - N clients = analyse multiple
    
    **Détection automatique !**
    """)

st.divider()

if not uploaded:
    st.info(" En attente d'un fichier PDF ou ZIP")
    st.stop()
upload_key = re.sub(r'[^a-zA-Z0-9]', '_', uploaded.name)
st.subheader("2 Traitement des documents")

with st.spinner(" Analyse du contenu"):
    workspace = Path(tempfile.mkdtemp(prefix="ifrs15_"))
    uploads_dir = workspace / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    uploaded_path = save_uploaded_file(uploaded, uploads_dir)

    if uploaded_path.suffix.lower() == ".zip":
        st.info(" ZIP détecté - Extraction en cours")

        extract_dir = workspace / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(uploaded_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)

        all_pdfs = list(extract_dir.rglob("*.pdf"))

        if not all_pdfs:
            st.error(" Aucun PDF trouvé dans le ZIP")
            st.stop()

        st.success(f"✓ {len(all_pdfs)} PDF(s) trouvé(s)")

        all_pdfs = deduplicate_versions(all_pdfs)

        if len(all_pdfs) < len(list(extract_dir.rglob("*.pdf"))):
            st.info(f"Après déduplication: {len(all_pdfs)} PDF(s) conservé(s)")

        with st.spinner(" Identification des clients en cours"):
            # Detect the real depth of client folders
            # Structure: ZIP > [optional same-name root folder] > ClientFolders > PDFs
            folder_groups = {}
            for pdf in all_pdfs:
                try:
                    rel = pdf.relative_to(extract_dir)
                    parts = rel.parts
                    # parts = ('RootFolder', 'ClientFolder', 'file.pdf') -> use parts[-2]
                    # parts = ('ClientFolder', 'file.pdf')               -> use parts[0]
                    # parts = ('file.pdf',)                              -> no folder
                    if len(parts) >= 3:
                        client_folder = parts[-2]  # Always the direct parent of the PDF
                    elif len(parts) == 2:
                        client_folder = parts[0]
                    else:
                        client_folder = None
                except ValueError:
                    client_folder = None
        
                if client_folder:
                    if client_folder not in folder_groups:
                        folder_groups[client_folder] = []
                    folder_groups[client_folder].append(pdf)
        
            # If all PDFs end up in one group named like the ZIP, it means
            # we captured the wrong level — check if that single group == zip name
            zip_stem = Path(uploaded.name).stem.strip()
            if len(folder_groups) == 1 and list(folder_groups.keys())[0].strip() == zip_stem:
                # Re-group using parts[-2] was already the root — go one level deeper
                folder_groups = {}
                for pdf in all_pdfs:
                    try:
                        rel = pdf.relative_to(extract_dir)
                        parts = rel.parts
                        client_folder = parts[1] if len(parts) >= 3 else None
                    except ValueError:
                        client_folder = None
                    if client_folder:
                        if client_folder not in folder_groups:
                            folder_groups[client_folder] = []
                        folder_groups[client_folder].append(pdf)
        
            if folder_groups:
                contracts_groups = folder_groups
            else:
                contracts_groups = group_pdfs_by_client_smart(
                    all_pdfs, client_list, zip_name=uploaded.name
                )

        st.success(f"✓ {len(contracts_groups)} client(s) détecté(s)")

        if len(contracts_groups) == 1:
            client_name = list(contracts_groups.keys())[0]
            pdfs = contracts_groups[client_name]

            st.info(f" **1 client détecté** : {client_name} ({len(pdfs)} document(s))")

            col1, col2 = st.columns([3, 1])
            with col1:
                client_name_corrected = st.text_input(
                    "Nom du client (modifiable)",
                    value=client_name,
                    key=f"client_name_{upload_key}"
                )
            with col2:
                st.caption("Vous pouvez corriger le nom")

            client_name = client_name_corrected

            contract_dir = workspace / "contract"
            contract_dir.mkdir(parents=True, exist_ok=True)
            for pdf in pdfs:
                shutil.copy2(pdf, contract_dir / pdf.name)

            contracts_to_analyze = [(client_name, contract_dir)]

        else:
            st.info(f" **{len(contracts_groups)} clients détectés** dans le ZIP")
            st.caption("Vérifiez et corrigez les noms si nécessaire avant de lancer l'analyse.")

            contracts_to_analyze = []

            for idx, (client_name, pdfs) in enumerate(contracts_groups.items()):
                col_name, col_docs = st.columns([2, 3])
                with col_name:
                    client_name_corrected = st.text_input(
                        f"Client {idx + 1}",
                        value=client_name,
                        key=f"zip_client_name_{idx}_{upload_key}",
                        help="Modifiez si la détection automatique est incorrecte"
                    )
                with col_docs:
                    st.markdown(f"**{len(pdfs)} document(s) :** " + ", ".join(f"`{p.name}`" for p in pdfs))

                contract_dir = workspace / f"contract_{idx}"
                contract_dir.mkdir(parents=True, exist_ok=True)
                for pdf in pdfs:
                    shutil.copy2(pdf, contract_dir / pdf.name)

                contracts_to_analyze.append((client_name_corrected, contract_dir))

    else:
        st.info(" PDF unique détecté")

        contract_dir = workspace / "contract"
        contract_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(uploaded_path, contract_dir / uploaded_path.name)

        detected_client = identify_client_for_pdf(uploaded_path, client_list, read_content=False)

        col1, col2 = st.columns([3, 1])
        with col1:
            client_name = st.text_input(
                "Nom du client détecté (modifiable)",
                value=detected_client,
                key=f"client_name_{upload_key}"
            )
        with col2:
            st.caption("Modifiez si incorrect")

        contracts_to_analyze = [(client_name, contract_dir)]

st.divider()

st.subheader("3 Configuration de l'analyse")

col1, col2 = st.columns(2)

with col1:
    if len(contracts_to_analyze) > 1:
        st.info(f" Analyse de {len(contracts_to_analyze)} clients détectés")
        contract_label = "Multiple"
    else:
        contract_label = st.text_input(
            "Nom du contrat / Client",
            value=contracts_to_analyze[0][0],
            key=f"contract_label_{upload_key}"
        )
        contracts_to_analyze[0] = (contract_label, contracts_to_analyze[0][1])

with col2:
    agi_threshold = st.number_input(
        "Seuil AGI IFRS15 (%)",
        min_value=0.0,
        max_value=100.0,
        value=SessionManager.get_config('agi_threshold'),
        step=0.5
    )

st.divider()

st.subheader("4 Lancement de l'analyse")

if st.button(" Analyser avec AWS", type="primary", use_container_width=True):

    all_results = []

    for idx, (client, contract_dir) in enumerate(contracts_to_analyze):

        if len(contracts_to_analyze) > 1:
            st.markdown(f"###  Client {idx+1}/{len(contracts_to_analyze)} : {client}")

        try:
            with st.spinner(f" Analyse AWS en cours pour {client}"):
                with suppress_stdout_stderr():
                    result_row, evidence = analyze_contract_real(
                        contract_dir=contract_dir,
                        agi_threshold=agi_threshold,
                        contract_label=client
                    )

            contract_data = {
                **result_row,
                'evidence': evidence,
                'files': [f.name for f in contract_dir.glob("*.pdf")]
            }
            SessionManager.add_contract(contract_data)

            all_results.append((client, result_row, evidence, contract_dir))
            st.success(f" Analyse terminée : {client}")

        except Exception as e:
            st.error(f" Erreur pour {client}: {str(e)}")
            import traceback
            with st.expander("Détails de l'erreur"):
                st.code(traceback.format_exc())
            continue

    if not all_results:
        st.error(" Aucune analyse n'a réussi")
        st.stop()

    st.session_state.analysis_results = all_results
    st.rerun()