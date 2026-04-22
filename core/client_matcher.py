import re
import unicodedata
from pathlib import Path
from typing import Optional
import pandas as pd

def _normalize(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def _tokens(text: str) -> set:
    return set(_normalize(text).split())


def _score(candidate: str, client: str) -> float:
    c_norm = _normalize(candidate)
    k_norm = _normalize(client)

    if not k_norm:
        return 0.0

    if c_norm == k_norm:
        return 1.0

    if k_norm in c_norm or c_norm in k_norm:
        return 0.9

    c_tokens = _tokens(candidate)
    k_tokens = _tokens(client)

    c_tokens = {t for t in c_tokens if len(t) >= 3}
    k_tokens = {t for t in k_tokens if len(t) >= 3}

    if not k_tokens:
        return 0.0

    intersection = c_tokens & k_tokens
    union = c_tokens | k_tokens

    if not union:
        return 0.0

    jaccard = len(intersection) / len(union)

    if k_tokens and k_tokens.issubset(c_tokens):
        jaccard = min(1.0, jaccard + 0.3)

    return jaccard


_CLIENT_LIST: Optional[list] = None


def load_client_list(excel_path: Optional[Path] = None) -> list:
    global _CLIENT_LIST

    if _CLIENT_LIST is not None:
        return _CLIENT_LIST

    search_paths = []
    if excel_path:
        search_paths.append(Path(excel_path))

    cwd = Path.cwd()
    project_root = Path(__file__).parent.parent

    for base in [cwd, project_root]:
        search_paths += [
            base / "clients.xlsx",
            base / "Clients.xlsx",
            base / "CLIENTS.xlsx",
            base / "clients.csv",
            base / "data" / "clients.xlsx",
        ]

    df = None
    for path in search_paths:
        if path.exists():
            try:
                if path.suffix.lower() in (".xlsx", ".xls"):
                    df = pd.read_excel(path)
                else:
                    df = pd.read_csv(path)
                break
            except Exception:
                continue

    if df is None:
        _CLIENT_LIST = []
        return _CLIENT_LIST

    candidate_cols = ["Client", "client", "CLIENT", "Nom", "nom",
                      "Name", "name", "Customers", "customers"]
    col = None
    for c in candidate_cols:
        if c in df.columns:
            col = c
            break

    if col is None:
        col = df.columns[0]

    clients = df[col].dropna().astype(str).str.strip().tolist()
    clients = [c for c in clients if c]

    _CLIENT_LIST = clients
    return _CLIENT_LIST


def reload_client_list():
    global _CLIENT_LIST
    _CLIENT_LIST = None

MATCH_THRESHOLD = 0.45
ZIP_MATCH_THRESHOLD = 0.6


def match_client_from_filename(filename: str, client_list: list) -> Optional[str]:
    if not client_list:
        return None

    best_client = None
    best_score = 0.0

    for client in client_list:
        s = _score(filename, client)
        if s > best_score:
            best_score = s
            best_client = client

    if best_score >= MATCH_THRESHOLD:
        return best_client
    return None


def match_client_from_text(text: str, client_list: list) -> Optional[str]:
    if not client_list or not text:
        return None

    header = text[:3000]

    best_client = None
    best_score = 0.0

    for client in client_list:
        s = _score(header, client)
        if s > best_score:
            best_score = s
            best_client = client

    if best_score >= MATCH_THRESHOLD:
        return best_client
    return None


def match_zip_name_to_client(zip_name: str, client_list: list) -> Optional[str]:
    if not client_list or not zip_name:
        return None

    zip_stem = Path(zip_name).stem if '.' in zip_name else zip_name

    best_client = None
    best_score = 0.0

    for client in client_list:
        s = _score(zip_stem, client)
        if s > best_score:
            best_score = s
            best_client = client

    if best_score >= ZIP_MATCH_THRESHOLD:
        return best_client
    return None


def _extract_futurmaster_client(text: str) -> str:
    if not text:
        return None

    match = re.search(
        r"FuturMaster\s*/\s*([A-ZÀ-Ÿa-zà-ÿ][A-ZÀ-Ÿa-zà-ÿ0-9\s&.,'-]{2,60})",
        text,
        re.IGNORECASE
    )
    if match:
        candidate = match.group(1).strip()
        candidate = candidate.splitlines()[0].strip()
        candidate = re.sub(r"\s+", " ", candidate).strip()
        if len(candidate) >= 2 and "futurmaster" not in candidate.lower():
            return candidate
    return None


def _quick_extract_pdf_text(pdf_path: Path, max_pages: int = 3) -> str:
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        text = ""
        for i in range(min(max_pages, len(doc))):
            text += doc[i].get_text()
        doc.close()
        return text
    except Exception:
        return ""


def identify_client_for_pdf(
    pdf_path: Path,
    client_list: list,
    read_content: bool = True
) -> str:
    """
    Identifie le client d'un PDF individuel.

    Ordre de priorité :
    1. Pattern "FuturMaster / CLIENT" dans le contenu
    2. Matching nom de fichier vs liste clients
    3. Matching contenu PDF vs liste clients
    4. Fallback : nom de fichier nettoyé
    5. "Inconnu"
    """
    filename = pdf_path.stem

    if read_content:
        text = _quick_extract_pdf_text(pdf_path)
        fm_client = _extract_futurmaster_client(text)
        if fm_client:
            if client_list:
                matched = match_client_from_text(fm_client, client_list)
                if matched:
                    return matched
                return fm_client
            else:
                return fm_client
    else:
        text = None

    if client_list:
        client = match_client_from_filename(filename, client_list)
        if client:
            return client

    if client_list and read_content:
        if text is None:
            text = _quick_extract_pdf_text(pdf_path)
        if text:
            client = match_client_from_text(text, client_list)
            if client:
                return client

    fallback = _clean_filename_as_client(filename)
    if fallback and fallback != "Inconnu":
        return fallback

    return "Inconnu"


def _clean_filename_as_client(filename: str) -> str:
    name = filename
    name = re.sub(r"^\d+[_\-\s]+", "", name)

    technical = {
        "futurmaster", "standard", "contract", "contracts", "service", "services",
        "conditions", "particulieres", "descriptif", "modalites",
        "annexe", "procedure", "modification", "generales",
        "fourniture", "sow", "drp", "cloud", "agreement", "addendum",
        "schedule", "order", "form", "master", "saas", "avenant",
        "amendment", "version", "final", "june", "july", "january",
        "february", "march", "april", "may", "august", "september",
        "october", "november", "december", "janvier", "fevrier", "mars",
        "avril", "juin", "juillet", "aout", "septembre", "octobre",
        "novembre", "decembre", "msa", "nda", "sla", "pdf", "doc", "docx",
        "2024", "2025", "2026", "2023", "2022",
        "du", "de", "des", "le", "la", "les", "un", "une",
        "au", "aux", "en", "par", "sur", "pour", "dans", "avec",
        "et", "ou", "mais", "donc", "car", "ni", "or",
        "a", "b", "c", "d", "e", "f", "g", "h",
        "mise", "place", "client", "fm", "contrat", "generaux",
        "professionnels", "prerequis", "prequis",
    }

    parts = re.split(r"[_\-\s]+", name)

    for part in parts:
        p_norm = _normalize(part)
        if p_norm in technical:
            continue
        if re.match(r"^\d+$", part):
            continue
        if re.match(r"^v\d+(\.\d+)*$", part, re.IGNORECASE):
            continue
        if len(part) < 2:
            continue
        return part.upper() if part.isupper() or len(part) <= 4 else part.title()

    return "Inconnu"

def _merge_similar_groups(groups: dict) -> dict:
    if len(groups) <= 1:
        return groups

    keys = sorted(groups.keys(), key=lambda k: len(_normalize(k)))
    merged = {k: list(v) for k, v in groups.items()}
    absorbed = set()

    for i, key_a in enumerate(keys):
        if key_a in absorbed:
            continue
        norm_a = _normalize(key_a)

        for key_b in keys[i + 1:]:
            if key_b in absorbed:
                continue
            norm_b = _normalize(key_b)

            should_merge = False
            if norm_b.startswith(norm_a) or norm_a.startswith(norm_b):
                should_merge = True

            if not should_merge:
                score = _score(key_a, key_b)
                if score >= 0.6:
                    should_merge = True

            if should_merge:
                merged[key_a].extend(merged[key_b])
                absorbed.add(key_b)

    return {k: v for k, v in merged.items() if k not in absorbed}


def _detect_common_batch_token(pdf_files: list) -> str:
    if len(pdf_files) < 2:
        return None

    def get_tokens(path):
        name = path.stem.lower()
        return set(re.split(r"[_\-\s]+", name))

    token_sets = [get_tokens(p) for p in pdf_files]
    common = token_sets[0]
    for s in token_sets[1:]:
        common &= s

    for token in common:
        if re.match(r"^\d{4,8}$", token):
            return token
        if re.match(r"^[a-z]{1,3}\d{2,6}$", token):
            return token

    return None


def _best_client_name_for_batch(pdf_files: list, client_list: list) -> str:
    if not client_list:
        return _fallback_name_from_filenames(pdf_files)

    fm_votes: dict = {}
    for pdf in pdf_files:
        text = _quick_extract_pdf_text(pdf)
        fm_client = _extract_futurmaster_client(text) if text else None
        if fm_client:
            if client_list:
                matched = match_client_from_text(fm_client, client_list)
                key = matched if matched else fm_client
            else:
                key = fm_client
            fm_votes[key] = fm_votes.get(key, 0) + 1

    if fm_votes:
        best = max(fm_votes, key=lambda k: fm_votes[k])
        return best

    for pdf in pdf_files:
        s = match_client_from_filename(pdf.stem, client_list)
        if s:
            best_score = max(_score(pdf.stem, c) for c in client_list)
            if best_score >= 0.7:
                return s

    scores_content: dict = {c: 0.0 for c in client_list}
    pdfs_read = 0

    for pdf in pdf_files:
        text = _quick_extract_pdf_text(pdf)
        if not text:
            continue
        pdfs_read += 1
        header = text[:3000]
        for client in client_list:
            s = _score(header, client)
            scores_content[client] += s

    if pdfs_read > 0:
        best_client_content = max(scores_content, key=lambda c: scores_content[c])
        best_score_content = scores_content[best_client_content]
        if best_score_content >= 0.4:
            return best_client_content

    return _fallback_name_from_filenames(pdf_files)


def _fallback_name_from_filenames(pdf_files: list) -> str:
    stopwords = {"du", "de", "des", "le", "la", "au", "en", "fm", "drp", "sow",
                 "v1", "v2", "v3", "msa", "nda", "sla"}
    candidates = []
    for pdf in pdf_files:
        name = _clean_filename_as_client(pdf.stem)
        if name and name != "Inconnu" and name.lower() not in stopwords and len(name) >= 3:
            candidates.append((len(name), name))
    if candidates:
        candidates.sort()
        return candidates[0][1]
    return "Inconnu"


def group_pdfs_by_client_smart(
    pdf_files: list,
    client_list: list,
    progress_callback=None,
    zip_name: Optional[str] = None
) -> dict:
    """
    Groupe une liste de PDFs par client.

    Ordre de priorité :
    0. Nom du ZIP → si match avec clients.xlsx → TOUS les PDFs = ce client
       (cas "Nutrition et Santé.zip" → "NUTRITION ET SANTE FRANCE")
    1. Token commun dans les noms de fichiers → batch mono-client
    2. Identification individuelle par PDF
    3. Fusion des groupes similaires

    Args:
        pdf_files: Liste de Path vers les PDFs
        client_list: Liste des clients connus (depuis Excel)
        progress_callback: Fonction optionnelle pour la progression
        zip_name: Nom du fichier ZIP uploadé (avec ou sans extension)
    """
    if not pdf_files:
        return {}

    if len(pdf_files) == 1:
        if zip_name and client_list:
            client_from_zip = match_zip_name_to_client(zip_name, client_list)
            if client_from_zip:
                return {client_from_zip: [pdf_files[0]]}
        client = identify_client_for_pdf(pdf_files[0], client_list)
        return {client: [pdf_files[0]]}

    if zip_name and client_list:
        client_from_zip = match_zip_name_to_client(zip_name, client_list)
        if client_from_zip:
            if progress_callback:
                progress_callback(
                    f"Client identifié depuis le nom du ZIP : '{client_from_zip}' "
                    f"({len(pdf_files)} document(s) regroupés)"
                )
            return {client_from_zip: list(pdf_files)}

    batch_token = _detect_common_batch_token(pdf_files)
    if batch_token:
        if progress_callback:
            progress_callback(f"Token commun détecté : '{batch_token}' → batch mono-client")
        client_name = _best_client_name_for_batch(pdf_files, client_list)
        return {client_name: list(pdf_files)}

    groups: dict = {}

    for i, pdf in enumerate(pdf_files):
        if progress_callback:
            progress_callback(f"Identification client {i+1}/{len(pdf_files)} : {pdf.name}")

        client = identify_client_for_pdf(pdf, client_list, read_content=True)

        if client not in groups:
            groups[client] = []
        groups[client].append(pdf)

    groups = _merge_similar_groups(groups)

    return groups