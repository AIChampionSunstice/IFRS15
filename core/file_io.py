from pathlib import Path
import zipfile

def save_uploaded_file(uploaded_file, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / uploaded_file.name
    with open(out_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return out_path

def extract_zip_to_dir(zip_path: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        for member in z.namelist():
            member_path = (dest_dir / member).resolve()
            if not str(member_path).startswith(str(dest_dir.resolve())):
                raise ValueError("ZIP invalide (zip-slip).")
        z.extractall(dest_dir)

def list_files_recursive(root: Path):
    exts = {".pdf", ".docx"}
    files = []
    for fp in root.rglob("*"):
        if fp.is_file() and fp.suffix.lower() in exts:
            files.append(fp)
    return files

def exporter_resultats(contracts, chemin="evaluation/sorties/run1.xlsx"):
    """Exporte les analyses pour l'évaluation IFRS 15."""
    import pandas as pd

    lignes = []

    for c in contracts:
        ligne = {
            k: v
            for k, v in c.items()
            if k not in ("sources", "evidence", "files", "reasoning")
        }

        for champ, src in (c.get("sources") or {}).items():
            ligne[f"source {champ}"] = src

        lignes.append(ligne)

    Path(chemin).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(lignes).to_excel(chemin, index=False)

    return chemin