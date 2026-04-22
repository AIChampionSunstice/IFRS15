from pathlib import Path
from typing import Dict, Tuple
from .aws_services import AWSServices
import streamlit as st
import re

def _norm(s: str) -> str:
    return (s or "").strip().lower()

def apply_ifrs_rules(result: Dict, agi_threshold: float) -> Dict:
    if not isinstance(result, dict):
        return result

    ramp_reason = _norm(result.get("Ramp up price"))
    pct_key = "Ramp-up price % TCV"
    ifrs_key = "IFRS 15 AGI"

    pure_perimeter_values = {
        "périmètre", "perimetre", "périmetre",
        "scope", "perimeter"
    }

    if ramp_reason in pure_perimeter_values:
        result[pct_key] = 0
        result[ifrs_key] = "Yes"
        return result

    try:
        pct = float(result.get(pct_key, 0) or 0)
    except Exception:
        pct = 0.0

    result[pct_key] = pct
    try:
        threshold = float(agi_threshold)
    except Exception:
        threshold = 0.0

    result[ifrs_key] = "Yes" if pct < threshold else "No"
    return result


def _extract_money_amounts(text: str) -> list:
    if not text:
        return []

    candidates = re.findall(
        r"(\d{1,3}(?:[ \.,]\d{3})*(?:[ \.,]\d+)?)\s*(€|euros|euro)\b",
        text,
        flags=re.IGNORECASE
    )

    nums = []
    for number_str, _unit in candidates:
        s = number_str.strip().replace(" ", "").replace(",", "").replace(".", "")
        try:
            nums.append(int(s))
        except Exception:
            pass

    return nums


def format_duration_human(result: Dict) -> Dict:
    if not isinstance(result, dict):
        return result

    duration_str = result.get("Durée du Contrat", "")

    if not duration_str or duration_str == "Not found":
        return result

    match = re.search(r'(\d+)\s*(mois|months|ans|years)', duration_str, re.IGNORECASE)

    if not match:
        return result

    number = int(match.group(1))
    unit = match.group(2).lower()

    if unit in ['ans', 'years']:
        return result

    if number % 12 == 0:
        years = number // 12
        result["Durée du Contrat"] = f"{years} an{'s' if years > 1 else ''}"
    elif number == 18:
        result["Durée du Contrat"] = "1 an et demi"
    elif number == 30:
        result["Durée du Contrat"] = "2 ans et demi"
    elif number > 12:
        years = number // 12
        months = number % 12
        result["Durée du Contrat"] = f"{years} an{'s' if years > 1 else ''} et {months} mois"
    else:
        result["Durée du Contrat"] = f"{number} mois"

    return result


def fix_setup_fees(result: Dict, evidence: Dict | None = None) -> Dict:
    if not isinstance(result, dict):
        return result

    sources = result.get("sources", {}) or {}
    setup_src = sources.get("Setup fees") or sources.get("Setup fees €") or ""

    if setup_src and setup_src != "Not found":
        amounts = _extract_money_amounts(setup_src)
        if amounts:
            result["Setup fees €"] = max(amounts)
            result["Setup fees"] = "Yes"
            return result

    current = result.get("Setup fees €", 0)
    if current and current > 0:
        result["Setup fees"] = "Yes"
    else:
        result["Setup fees €"] = 0
        result["Setup fees"] = "No"

    return result


def validate_result_quality(result: Dict) -> Dict:
    date_fields = ["Date signature", "SaaS Start Date", "End date théorique"]

    for field in date_fields:
        date_value = result.get(field, "")
        if date_value and date_value not in ["Not found", "N/A", ""]:
            if not re.match(r'\d{2}/\d{2}/\d{4}', date_value):
                result[field] = "Not found"
                if "reasoning" in result:
                    result["reasoning"] += f"\n {field} invalide (format non DD/MM/YYYY) → Not found"

    amount_fields = ["Ramp up price impact € vs TCV", "Setup fees €"]
    for field in amount_fields:
        amount = result.get(field, 0)
        try:
            if float(amount) < 0:
                result[field] = 0
        except Exception:
            result[field] = 0

    if "Ramp-up price % TCV" in result:
        try:
            pct = float(result["Ramp-up price % TCV"])
            if pct < 0 or pct > 100:
                result["Ramp-up price % TCV"] = 0
        except Exception:
            result["Ramp-up price % TCV"] = 0

    return result


def sanitize_rampup_value(result: Dict) -> Dict:
    if not isinstance(result, dict):
        return result

    raw = _norm(result.get("Ramp up price", ""))

    if not raw or raw in ("not found", "n/a", "none", ""):
        if result.get("Price Ramp-up") == "No":
            result["Ramp up price"] = "No"
        return result

    has_peri = any(x in raw for x in ["périmètre", "perimetre", "perimeter", "scope"])
    has_comm = any(x in raw for x in ["commercial", "comm"])

    if has_peri and has_comm:
        result["Ramp up price"] = "Périmètre + Commercial"
    elif has_peri:
        result["Ramp up price"] = "Périmètre"
    elif has_comm:
        result["Ramp up price"] = "Commercial"
    elif raw == "tbd":
        result["Ramp up price"] = "TBD"

    return result


def analyze_contract_real(
    contract_dir: Path,
    agi_threshold: float,
    contract_label: str
) -> Tuple[Dict, Dict]:
    """
    Analyse réelle avec AWS Bedrock + Textract + S3
    VERSION MULTI-DOCS INTELLIGENT
    """

    aws = AWSServices()

    progress_bar = st.progress(0, text="Initialisation")
    status_text = st.empty()

    files = list(contract_dir.rglob("*.pdf"))
    if not files:
        raise Exception("Aucun fichier PDF trouvé")

    total_steps = len(files) * 2 + 1
    current_step = 0

    status_text.text("Upload des documents vers S3")
    uploaded_files = []

    for file_path in files:
        s3_key = f"contracts/{contract_label}/{file_path.name}"
        s3_url = aws.upload_to_s3(file_path, s3_key)
        uploaded_files.append(s3_url)
        current_step += 1
        progress_bar.progress(current_step / total_steps, text=f"Upload {current_step}/{total_steps}")

    status_text.text("Extraction du texte avec Textract")
    texts_dict = {}

    for file_path in files:
        s3_key = f"contracts/{contract_label}/{file_path.name}"
        text = aws.extract_text_with_textract(s3_key)
        doc_type = aws.classify_document_type(text)
        texts_dict[f"{doc_type} ({file_path.name})"] = text
        current_step += 1
        progress_bar.progress(current_step / total_steps, text=f"Extraction {current_step}/{total_steps}")

    progress_bar.progress(0.95, text="Analyse IA avec Claude")
    status_text.text("Analyse IA en cours avec AWS Bedrock")

    if len(files) > 1:
        result, evidence = aws.analyze_multi_documents(texts_dict, agi_threshold, contract_label)
    else:
        all_text = list(texts_dict.values())[0]
        result, evidence = aws.analyze_with_bedrock(all_text, agi_threshold, contract_label)

    result = sanitize_rampup_value(result)
    result = apply_ifrs_rules(result, agi_threshold)
    result = fix_setup_fees(result, evidence)
    result = format_duration_human(result)
    result = validate_result_quality(result)

    progress_bar.progress(1.0, text="Analyse terminée ")
    status_text.text("Analyse terminée avec succès")

    evidence['uploaded_files'] = uploaded_files
    evidence['total_files'] = len(files)
    evidence['text_extracted_length'] = sum(len(t) for t in texts_dict.values())
    evidence['documents_types'] = list(texts_dict.keys())

    return result, evidence