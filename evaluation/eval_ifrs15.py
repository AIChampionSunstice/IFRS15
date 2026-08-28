#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Évaluation automatisée du système d'analyse de contrats IFRS 15.

Produit, à partir du classeur de vérité terrain et des sorties du système :
  - Tableau 6.1 : exactitude par champ (correct, précision, rappel, erreur dominante)
  - Tableau 6.2 : distribution des erreurs par type (T0-T4)
  - Tableau 6.3 : matrice de confusion sur la décision IFRS 15
  - Tableau 6.6 : reproductibilité sur exécutions répétées (option --runs)
  - Tableau 6.5 : accord inter-modèles (option --runs avec 2 fichiers de modèles différents)

USAGE
-----
  pip install pandas openpyxl unidecode

  # Évaluation principale (exactitude + décision)
  python eval_ifrs15.py --vt verite_terrain.xlsx --ia sortie_ia.xlsx

  # Si les deux blocs sont dans la MÊME feuille l'un sous l'autre (comme dans ta capture) :
  python eval_ifrs15.py --fichier classeur.xlsx --split-auto

  # Reproductibilité : plusieurs exécutions du même modèle
  python eval_ifrs15.py --vt verite_terrain.xlsx --runs run1.xlsx run2.xlsx run3.xlsx

Les sorties sont écrites en Markdown (collables dans Word) et en CSV.
"""

import argparse
import re
import sys
import unicodedata
from datetime import datetime

import pandas as pd

# ---------------------------------------------------------------------------
# 1. DÉFINITION DES CHAMPS
#    Adapte les libellés de la colonne "col" aux en-têtes exacts de ton fichier.
#    "kind" pilote la normalisation ; "role" distingue extraction et décision.
# ---------------------------------------------------------------------------

CHAMPS = [
    dict(nom="Client",                        col="Client Name",                    kind="text",     role="cle"),
    dict(nom="Type de contrat",               col="Type de contrat",                kind="cat",      role="extraction"),
    dict(nom="Contrat format standard",       col="Contrat format Sunstice",        kind="bool",     role="extraction"),
    dict(nom="Date de signature",             col="Date signature",                 kind="date",     role="extraction"),
    dict(nom="Périmètre souscrit",            col="Scope",                          kind="text",     role="extraction"),
    dict(nom="Durée du contrat",              col="Durée du Contrat",               kind="duree",    role="extraction"),
    dict(nom="Présence d'un ramp-up",         col="Price Ramp-up",                  kind="bool",     role="extraction"),
    dict(nom="Type de ramp-up",               col="Ramp up price type",             kind="rampup",   role="extraction"),
    dict(nom="Impact du ramp-up",             col="Ramp up price impact R vs T",    kind="montant",  role="extraction"),
    dict(nom="Devise",                        col="Devise en Euro",                 kind="montant",  role="extraction"),
    dict(nom="Ramp-up en % du TCV",           col="Ramp-up price % TCV",            kind="pct",      role="extraction"),
    dict(nom="Conformité IFRS 15",            col="IFRS 15 AGI",                    kind="bool",     role="decision"),
    dict(nom="Option de sortie",              col="Option Sortie avant terme du contrat", kind="text", role="extraction"),
    dict(nom="Date de début SaaS",            col="SaaS Start Date",                kind="date",     role="extraction"),
    dict(nom="Date de démarrage effectif",    col="Start date ignition",            kind="date",     role="extraction"),
    dict(nom="Date de fin théorique",         col="End date théorique",             kind="date",     role="extraction"),
    dict(nom="Présence de setup fees",        col="Setup fees",                     kind="bool",     role="extraction"),
    dict(nom="Montant des setup fees",        col="Setup fees Montant",             kind="montant",  role="extraction"),
]

# Valeurs signalant que le système n'a pas trouvé l'information
MARQUEURS_NON_TROUVE = [
    "not found", "non trouvé", "non trouve", "n/a", "na", "nan", "none",
    "non signé", "non signe", "not explicitly stated", "not specified",
    "cannot calculate", "unknown", "inconnu", "-", "",
]

# Valeurs signalant que la référence elle-même est indisponible (document illisible)
MARQUEURS_ILLISIBLE = [
    "image de mauvaise qualite", "mauvaise qualite", "illisible",
    "texte à trouver", "texte a trouver", "à trouver dans le contrat",
    "complexe", "pas specifie", "pas spécifié",
]

TOLERANCE_MONTANT = 0.01   # 1 % d'écart relatif toléré sur les montants
TOLERANCE_PCT     = 0.5    # 0,5 point toléré sur les pourcentages


# ---------------------------------------------------------------------------
# 2. NORMALISATION
# ---------------------------------------------------------------------------

def _base(v):
    """Minuscules, sans accents, espaces compressés."""
    if v is None:
        return ""
    s = str(v).strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).lower()


def est_non_trouve(v):
    s = _base(v)
    return s in MARQUEURS_NON_TROUVE or any(m in s for m in MARQUEURS_NON_TROUVE if len(m) > 4)


def est_illisible(v):
    s = _base(v)
    return any(m in s for m in MARQUEURS_ILLISIBLE)


def norm_bool(v):
    s = _base(v)
    if est_non_trouve(v):
        return None
    if s.startswith(("yes", "oui", "y", "true", "vrai", "1")):
        return "OUI"
    if s.startswith(("no", "non", "n", "false", "faux", "0")):
        return "NON"
    return s or None


def norm_date(v):
    """Ramène toute date à AAAA-MM-JJ. Gère les Timestamp pandas et les formats FR/US."""
    if est_non_trouve(v):
        return None
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.strftime("%Y-%m-%d")
    s = _base(v)
    m = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", s)
    if m:
        j, mo, a = m.groups()
        a = ("20" + a) if len(a) == 2 else a
        try:
            return datetime(int(a), int(mo), int(j)).strftime("%Y-%m-%d")
        except ValueError:
            pass
    m = re.search(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})", s)
    if m:
        a, mo, j = m.groups()
        try:
            return datetime(int(a), int(mo), int(j)).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def norm_duree(v):
    """Convertit toute durée en nombre de mois. '36 mois' == '3 ans' == '3'."""
    if est_non_trouve(v):
        return None
    s = _base(v)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(mois|month|m\b)", s)
    if m:
        return round(float(m.group(1).replace(",", ".")))
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(ans?|an\b|year|yr)", s)
    if m:
        return round(float(m.group(1).replace(",", ".")) * 12)
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)", s)
    if m:  # nombre nu : convention = années si <= 10, sinon mois
        x = float(m.group(1).replace(",", "."))
        return round(x * 12) if x <= 10 else round(x)
    return None


def norm_montant(v):
    if est_non_trouve(v):
        return None
    if isinstance(v, (int, float)) and not pd.isna(v):
        return float(v)
    s = _base(v)
    s = re.sub(r"[€$£\s]", "", s)
    m = re.search(r"-?\d[\d ]*(?:[.,]\d+)?", s)
    if not m:
        return None
    x = m.group(0).replace(" ", "")
    if "," in x and "." in x:
        x = x.replace(".", "").replace(",", ".") if x.rfind(",") > x.rfind(".") else x.replace(",", "")
    else:
        x = x.replace(",", ".")
    try:
        return float(x)
    except ValueError:
        return None


def norm_pct(v):
    x = norm_montant(v)
    return None if x is None else round(x, 2)


def norm_rampup(v):
    """Périmètre vs commercial, quelle que soit la langue."""
    if est_non_trouve(v):
        return None
    s = _base(v)
    if "perimetre" in s or "scope" in s or "ramp" in s and "perim" in s:
        return "PERIMETRE"
    if "commercial" in s or "geste" in s or "discount" in s or "remise" in s:
        return "COMMERCIAL"
    return s or None


def norm_cat(v):
    if est_non_trouve(v):
        return None
    s = _base(v)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return " ".join(sorted(set(s.split()))) or None


def norm_text(v):
    if est_non_trouve(v):
        return None
    s = _base(v)
    return re.sub(r"[^a-z0-9]+", " ", s).strip() or None


NORMALISEURS = {
    "bool": norm_bool, "date": norm_date, "duree": norm_duree,
    "montant": norm_montant, "pct": norm_pct, "rampup": norm_rampup,
    "cat": norm_cat, "text": norm_text,
}


# ---------------------------------------------------------------------------
# 3. COMPARAISON ET TYPOLOGIE D'ERREURS
# ---------------------------------------------------------------------------

def comparer(vt_brut, ia_brut, kind):
    """Retourne (correct: bool|None, type_erreur: str).

    None = comparaison impossible (référence illisible) -> exclu des métriques.
    Types : T0 absence correctement signalée, T1 prudence excessive,
            T2 erreur de valeur, T3 erreur de qualification,
            T4 format/langue (valeur juste après normalisation seulement).
    """
    if est_illisible(vt_brut):
        return None, "EXCLU"

    f = NORMALISEURS[kind]
    vt, ia = f(vt_brut), f(ia_brut)

    if vt is None and ia is None:
        return True, "T0"
    if vt is None and ia is not None:
        return False, "T2"          # le système invente une valeur absente de la référence
    if vt is not None and ia is None:
        return False, "T1"          # prudence excessive

    if kind == "montant":
        if vt == 0 and ia == 0:
            egal = True
        else:
            denom = max(abs(vt), abs(ia), 1e-9)
            egal = abs(vt - ia) / denom <= TOLERANCE_MONTANT
    elif kind == "pct":
        egal = abs(vt - ia) <= TOLERANCE_PCT
    elif kind == "text":
        egal = vt == ia or vt in ia or ia in vt
    else:
        egal = vt == ia

    if egal:
        # Écart de surface neutralisé par la normalisation -> T4 signalé, mais correct
        if _base(vt_brut) != _base(ia_brut):
            return True, "T4"
        return True, "OK"

    return False, ("T3" if kind in ("rampup", "bool", "cat") else "T2")


# ---------------------------------------------------------------------------
# 4. CHARGEMENT
# ---------------------------------------------------------------------------

def trouver_colonne(df, libelle):
    """Appariement tolérant des en-têtes (tronqués, accentués, casse différente)."""
    cible = _base(libelle)
    for c in df.columns:
        if _base(c) == cible:
            return c
    for c in df.columns:
        b = _base(c)
        if b and (b in cible or cible in b) and len(b) >= 4:
            return c
    return None


def charger(path, sheet=0):
    df = pd.read_excel(path, sheet_name=sheet) if str(path).endswith((".xlsx", ".xls")) \
        else pd.read_csv(path)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def split_auto(path, sheet=0):
    """Sépare les deux blocs 'Vérité Terrain' et 'Ce que sort l'IA' d'une même feuille."""
    raw = pd.read_excel(path, sheet_name=sheet, header=None)
    marqueurs = []
    for i, row in raw.iterrows():
        txt = _base(" ".join(str(x) for x in row.tolist() if pd.notna(x)))
        if "verite terrain" in txt:
            marqueurs.append(("VT", i))
        elif "sort l'ia" in txt or "sort l ia" in txt or "ce que sort" in txt:
            marqueurs.append(("IA", i))
    if len(marqueurs) < 2:
        sys.exit("Impossible de détecter les deux blocs. Utilise --vt et --ia avec deux fichiers.")
    (_, i_vt), (_, i_ia) = marqueurs[0], marqueurs[1]
    vt = pd.read_excel(path, sheet_name=sheet, header=i_vt + 1, nrows=i_ia - i_vt - 2)
    ia = pd.read_excel(path, sheet_name=sheet, header=i_ia + 1)
    for d in (vt, ia):
        d.columns = [str(c).strip() for c in d.columns]
        d.dropna(how="all", inplace=True)
    return vt, ia


def aligner(vt, ia, col_cle):
    """Aligne les deux tableaux sur la clé client (ordre non garanti)."""
    kvt, kia = trouver_colonne(vt, col_cle), trouver_colonne(ia, col_cle)
    if kvt is None or kia is None:
        n = min(len(vt), len(ia))
        print("! Clé client introuvable : alignement positionnel sur %d lignes." % n)
        return vt.head(n).reset_index(drop=True), ia.head(n).reset_index(drop=True)
    vt = vt.copy(); ia = ia.copy()
    vt["_k"] = vt[kvt].map(_base); ia["_k"] = ia[kia].map(_base)
    communs = [k for k in vt["_k"] if k in set(ia["_k"]) and k]
    vt = vt[vt["_k"].isin(communs)].drop_duplicates("_k").set_index("_k").loc[communs]
    ia = ia[ia["_k"].isin(communs)].drop_duplicates("_k").set_index("_k").loc[communs]
    return vt.reset_index(), ia.reset_index()


# ---------------------------------------------------------------------------
# 5. ÉVALUATION
# ---------------------------------------------------------------------------

def evaluer(vt, ia):
    lignes, erreurs, decision = [], [], []
    n = len(vt)

    for ch in CHAMPS:
        if ch["role"] == "cle":
            continue
        cvt, cia = trouver_colonne(vt, ch["col"]), trouver_colonne(ia, ch["col"])
        if cvt is None or cia is None:
            print("! Colonne absente, champ ignoré : %s (cherché : %s)" % (ch["nom"], ch["col"]))
            continue

        ok = exclus = 0
        vp = fp = fn = 0          # pour précision / rappel : "le système produit une valeur"
        types = {}

        for i in range(n):
            res, typ = comparer(vt[cvt].iloc[i], ia[cia].iloc[i], ch["kind"])
            if res is None:
                exclus += 1
                continue
            types[typ] = types.get(typ, 0) + 1
            if res:
                ok += 1
            else:
                erreurs.append(dict(champ=ch["nom"], ligne=i + 1, type=typ,
                                    reference=vt[cvt].iloc[i], systeme=ia[cia].iloc[i]))
            # précision / rappel sur la production de valeur
            a_vt = NORMALISEURS[ch["kind"]](vt[cvt].iloc[i]) is not None
            a_ia = NORMALISEURS[ch["kind"]](ia[cia].iloc[i]) is not None
            if a_ia and res:      vp += 1
            elif a_ia and not res: fp += 1
            elif a_vt and not a_ia: fn += 1

            if ch["role"] == "decision":
                decision.append((norm_bool(vt[cvt].iloc[i]), norm_bool(ia[cia].iloc[i])))

        eval_n = n - exclus
        dominant = max((t for t in types if t not in ("OK", "T0")),
                       key=lambda t: types[t], default="—")
        lignes.append(dict(
            Champ=ch["nom"], Role=ch["role"],
            Corrects="%d/%d" % (ok, eval_n) if eval_n else "—",
            Taux=round(100 * ok / eval_n, 1) if eval_n else None,
            Precision=round(100 * vp / (vp + fp), 1) if (vp + fp) else None,
            Rappel=round(100 * vp / (vp + fn), 1) if (vp + fn) else None,
            Exclus=exclus, Erreur_dominante=dominant))

    return pd.DataFrame(lignes), pd.DataFrame(erreurs), decision


def matrice_confusion(decision):
    vc = sum(1 for v, i in decision if v == "OUI" and i == "OUI")
    vn = sum(1 for v, i in decision if v == "NON" and i == "NON")
    fp = sum(1 for v, i in decision if v == "OUI" and i == "NON")
    fn = sum(1 for v, i in decision if v == "NON" and i == "OUI")
    return vc, vn, fp, fn


def reproductibilite(runs):
    """runs : liste de DataFrames alignés, issus d'exécutions successives."""
    lignes = []
    n = min(len(r) for r in runs)
    for ch in CHAMPS:
        if ch["role"] == "cle":
            continue
        cols = [trouver_colonne(r, ch["col"]) for r in runs]
        if any(c is None for c in cols):
            continue
        f = NORMALISEURS[ch["kind"]]
        stables = sum(1 for i in range(n)
                      if len({f(r[c].iloc[i]) for r, c in zip(runs, cols)}) == 1)
        lignes.append(dict(Champ=ch["nom"], Role=ch["role"],
                           Stables="%d/%d" % (stables, n),
                           Taux=round(100 * stables / n, 1)))
    return pd.DataFrame(lignes)


# ---------------------------------------------------------------------------
# 6. SORTIE
# ---------------------------------------------------------------------------

def md(df):
    return df.to_markdown(index=False)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--vt")
    p.add_argument("--ia")
    p.add_argument("--fichier")
    p.add_argument("--split-auto", action="store_true")
    p.add_argument("--sheet", default=0)
    p.add_argument("--runs", nargs="*", default=[])
    p.add_argument("--out", default="resultats_evaluation")
    a = p.parse_args()

    if a.split_auto:
        if not a.fichier:
            sys.exit("--split-auto requiert --fichier")
        vt, ia = split_auto(a.fichier, a.sheet)
    else:
        if not (a.vt and (a.ia or a.runs)):
            sys.exit("Fournis --vt et --ia (ou --runs).")
        vt = charger(a.vt, a.sheet)
        ia = charger(a.ia, a.sheet) if a.ia else charger(a.runs[0], a.sheet)

    vt, ia = aligner(vt, ia, "Client Name")
    print("Dossiers comparés : %d\n" % len(vt))

    tab, err, dec = evaluer(vt, ia)

    print("=== TABLEAU 6.1 — Exactitude par champ ===")
    print(md(tab[tab.Role == "extraction"].drop(columns="Role")))
    glob = tab[tab.Role == "extraction"]
    if len(glob):
        print("\nTaux global d'extraction : %.1f %%" % glob.Taux.mean())

    print("\n=== TABLEAU 6.2 — Distribution des erreurs ===")
    if len(err):
        d = err[err.type != "T4"].groupby("type").size().reset_index(name="Effectif")
        d["Part"] = (100 * d.Effectif / d.Effectif.sum()).round(1)
        d["Libellé"] = d.type.map({
            "T1": "Prudence excessive (« non trouvé » injustifié)",
            "T2": "Erreur de valeur",
            "T3": "Erreur de qualification",
        })
        print(md(d[["type", "Libellé", "Effectif", "Part"]]))
    else:
        print("Aucune erreur détectée.")

    if dec:
        vc, vn, fp, fn = matrice_confusion(dec)
        print("\n=== TABLEAU 6.3 — Matrice de confusion (décision IFRS 15) ===")
        print("|                        | Réf. conforme | Réf. non conforme |")
        print("|------------------------|---------------|-------------------|")
        print("| **Système : conforme**     | %d | %d (faux négatifs) |" % (vc, fn))
        print("| **Système : non conforme** | %d (faux positifs) | %d |" % (fp, vn))
        tot = vc + vn + fp + fn
        if tot:
            print("\nConcordance globale : %d/%d (%.1f %%)" % (vc + vn, tot, 100 * (vc + vn) / tot))
            print("Faux négatifs (non-conformités manquées) : %d — erreur la plus coûteuse." % fn)

    if len(a.runs) >= 2:
        runs = [aligner(vt, charger(r, a.sheet), "Client Name")[1] for r in a.runs]
        print("\n=== TABLEAU 6.6 — Reproductibilité sur %d exécutions ===" % len(runs))
        rep = reproductibilite(runs)
        print(md(rep.drop(columns="Role")))
        d = rep[rep.Role == "decision"]
        if len(d):
            print("\nStabilité de la décision de conformité : %s" % d.iloc[0].Stables)

    tab.to_csv(a.out + "_exactitude.csv", index=False)
    err.to_csv(a.out + "_erreurs.csv", index=False)
    print("\nFichiers écrits : %s_exactitude.csv, %s_erreurs.csv" % (a.out, a.out))
    print("Le second liste chaque erreur avec sa référence et la valeur du système :")
    print("c'est la matière première de l'analyse qualitative du §6.1.1 et du §6.2.")


if __name__ == "__main__":
    main()
