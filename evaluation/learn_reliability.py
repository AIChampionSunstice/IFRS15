#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EXPÉRIENCE B — Prédire la fiabilité d'une extraction plutôt que l'estimer.

Principe
--------
Le système IFRS 15 produit, pour chaque contrat, dix-sept champs assortis d'une
citation source. La vérité terrain établie avec la direction financière indique
lesquels sont corrects. Chaque couple (contrat, champ) constitue donc une
observation étiquetée, et l'on dispose d'un corpus supervisé de plusieurs
centaines d'exemples SANS AUCUNE ANNOTATION SUPPLÉMENTAIRE.

La tâche apprise n'est pas l'extraction elle-même mais sa fiabilité :
*ce champ sera-t-il correct ?* C'est une tâche d'estimation d'incertitude, et
elle porte directement sur le mécanisme central du système — l'escalade vers
vérification humaine.

Motivation
----------
Le système utilise aujourd'hui un score de confiance HEURISTIQUE, fondé sur des
paliers arbitraires (présence d'une source, longueur, présence de guillemets).
L'évaluation du prototype de notes de frais a par ailleurs montré qu'un
indicateur de confiance isolé ne prédit pas l'exactitude (r = 0,26). La question
posée ici est donc : *un modèle combinant plusieurs signaux fait-il mieux qu'une
heuristique à paliers ?*

Les signaux mobilisés incluent, lorsque disponibles, l'accord entre deux modèles
et la stabilité entre exécutions répétées — deux mesures qui ne requièrent pas
de vérité terrain et sont donc utilisables en production.

Protocole
---------
Validation croisée en laissant un CONTRAT de côté à chaque itération : les
champs d'un même contrat partagent le document, la mise en forme et la qualité
de numérisation ; les répartir entre apprentissage et test surestimerait la
performance.

USAGE
    python learn_reliability.py --vt verite_terrain.xlsx --ia sorties/run1.xlsx
    python learn_reliability.py --vt vt.xlsx --ia run1.xlsx \\
           --runs run2.xlsx run3.xlsx --modele2 opus.xlsx
"""

import argparse
import re
import unicodedata

import numpy as np
import pandas as pd

# Champs du référentiel IFRS 15. Adapter aux intitulés réels si nécessaire.
CHAMPS = [
    "Type de contrat", "Contrat format Sunstice", "Date signature", "Scope",
    "Durée du Contrat", "Price Ramp-up", "Ramp up price",
    "Ramp up price impact € vs TCV", "Ramp-up price % TCV",
    "Option Sortie avant terme du contrat", "SaaS Start Date",
    "Start date ignition", "End date théorique", "Setup fees", "Setup fees €",
]
CLE = "Client Name"
DECISION = "IFRS 15 AGI"

TYPES = {"date": ["Date signature", "SaaS Start Date", "Start date ignition",
                  "End date théorique"],
         "montant": ["Ramp up price impact € vs TCV", "Setup fees €",
                     "Ramp-up price % TCV"],
         "booleen": ["Contrat format Sunstice", "Price Ramp-up", "Setup fees"],
         "texte": ["Type de contrat", "Scope", "Durée du Contrat",
                   "Ramp up price", "Option Sortie avant terme du contrat"]}

NON_TROUVE = {"not found", "non trouvé", "non trouve", "n/a", "na", "none",
              "", "0", "nan", "-"}

NOMS = ["source_presente", "source_longueur", "source_a_citation",
        "source_a_page", "source_a_conclusion", "source_a_montant",
        "valeur_presente", "valeur_longueur", "valeur_est_defaut",
        "type_date", "type_montant", "type_booleen", "type_texte",
        "accord_inter_modeles", "stabilite_intra_modele",
        "nb_champs_non_trouves", "longueur_document", "part_champs_remplis"]


def _norm(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%d/%m/%Y")
    s = unicodedata.normalize("NFKD", str(v).strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    if s in NON_TROUVE:
        return None
    m = re.search(r"(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})", s)
    if m:
        return f"{int(m.group(3)):02d}/{int(m.group(2)):02d}/{m.group(1)}"
    m = re.fullmatch(r"[^\d]*(-?\d[\d\s]*(?:[.,]\d+)?)\s*[€%]?", s)
    if m:
        x = m.group(1).replace(" ", "").replace(",", ".")
        try:
            return f"{round(float(x), 2)}"
        except ValueError:
            pass
    return re.sub(r"[^a-z0-9]", "", s) or None


def _egal(a, b):
    if a is None or b is None:
        return a is None and b is None
    try:
        fa, fb = float(a), float(b)
        return abs(fa - fb) <= max(0.01, 0.01 * max(abs(fa), abs(fb)))
    except (TypeError, ValueError):
        return a == b


def charger(chemin):
    df = (pd.read_excel(chemin) if str(chemin).endswith((".xlsx", ".xls"))
          else pd.read_csv(chemin))
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _index(df):
    col = next((c for c in df.columns if _norm(c) == _norm(CLE)), df.columns[0])
    return {str(r[col]).strip().lower(): r for _, r in df.iterrows()}


def type_du_champ(champ):
    for t, liste in TYPES.items():
        if champ in liste:
            return t
    return "texte"


def descripteurs(ligne_ia, champ, sources, contexte, accord, stabilite):
    """Construit les descripteurs d'un couple (contrat, champ).

    Aucun descripteur ne suppose la connaissance de la vérité terrain : tous
    sont calculables en production, ce qui est la condition pour que le modèle
    soit utilisable comme critère d'escalade.
    """
    src = str(sources.get(champ, "") or "")
    val = ligne_ia.get(champ)
    vn = _norm(val)
    t = type_du_champ(champ)

    return [
        1.0 if src.strip() else 0.0,
        min(len(src), 300) / 300.0,
        1.0 if ('"' in src or "'" in src or "«" in src) else 0.0,
        1.0 if re.search(r"page\s*\d", src, re.I) else 0.0,
        1.0 if ("→" in src or "->" in src) else 0.0,
        1.0 if re.search(r"\d[\d\s.,]*\s*[€%]", src) else 0.0,
        1.0 if vn is not None else 0.0,
        min(len(str(val or "")), 80) / 80.0,
        1.0 if vn in ("0", "0.0", "no", "non") else 0.0,
        1.0 if t == "date" else 0.0,
        1.0 if t == "montant" else 0.0,
        1.0 if t == "booleen" else 0.0,
        1.0 if t == "texte" else 0.0,
        accord,
        stabilite,
        contexte["non_trouves"],
        contexte["longueur_doc"],
        contexte["part_remplis"],
    ]


def score_heuristique(sources, champ, valeur):
    """Réimplémente le score de confiance actuel de l'application.

    Sert de référence : le modèle appris doit faire mieux que cette heuristique
    pour justifier son adoption.
    """
    src = str(sources.get(champ, "") or "")
    if not src.strip():
        return 0
    if _norm(valeur) is None:
        return 30
    if re.search(r"non visible|non spécifié|à déterminer|pas trouvé|introuvable",
                 src, re.I):
        return 40
    if len(src) < 30:
        return 60
    if "'" in src or '"' in src or "→" in src:
        return 95
    return 80


def construire(vt_path, ia_path, runs=None, modele2=None, sources_path=None):
    vt, ia = _index(charger(vt_path)), _index(charger(ia_path))
    autres = [_index(charger(r)) for r in (runs or [])]
    m2 = _index(charger(modele2)) if modele2 else None
    srcs = _index(charger(sources_path)) if sources_path else None

    X, y, groupes, heur, meta = [], [], [], [], []
    communs = [k for k in ia if k in vt]
    print(f"Contrats appariés : {len(communs)}")

    for cle in communs:
        lia, lvt = ia[cle], vt[cle]
        sources = {}
        if srcs and cle in srcs:
            sources = {c: srcs[cle].get(c) for c in CHAMPS}
        else:
            for c in CHAMPS:
                for suffixe in (f"source {c}", f"{c} source", f"src {c}"):
                    col = next((k for k in lia.index
                                if _norm(k) == _norm(suffixe)), None)
                    if col:
                        sources[c] = lia[col]
                        break

        remplis = sum(1 for c in CHAMPS if _norm(lia.get(c)) is not None)
        contexte = dict(
            non_trouves=(len(CHAMPS) - remplis) / len(CHAMPS),
            longueur_doc=min(sum(len(str(lia.get(c, ""))) for c in CHAMPS),
                             2000) / 2000.0,
            part_remplis=remplis / len(CHAMPS))

        for champ in CHAMPS:
            if champ not in lvt.index:
                continue
            ref = _norm(lvt.get(champ))
            got = _norm(lia.get(champ))
            if ref is None and got is None:
                continue                     # rien à prédire

            accord = 0.5
            if m2 and cle in m2:
                accord = 1.0 if _egal(got, _norm(m2[cle].get(champ))) else 0.0
            stabilite = 0.5
            if autres:
                vals = [_norm(a[cle].get(champ)) for a in autres if cle in a]
                if vals:
                    stabilite = sum(1 for v in vals if _egal(v, got)) / len(vals)

            X.append(descripteurs(lia, champ, sources, contexte, accord,
                                  stabilite))
            y.append(int(_egal(ref, got)))
            groupes.append(cle)
            heur.append(score_heuristique(sources, champ, lia.get(champ)))
            meta.append((cle, champ))

    return (np.array(X, float), np.array(y), np.array(groupes),
            np.array(heur, float), meta)


def evaluer(X, y, groupes, heur, seed=0):
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import LeaveOneGroupOut
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    proba = np.zeros(len(y))
    proba_lr = np.zeros(len(y))
    for tr, te in LeaveOneGroupOut().split(X, y, groupes):
        if len(set(y[tr])) < 2:
            proba[te] = y[tr].mean()
            proba_lr[te] = y[tr].mean()
            continue
        gbm = HistGradientBoostingClassifier(max_iter=250, max_depth=3,
                                             random_state=seed).fit(X[tr], y[tr])
        proba[te] = gbm.predict_proba(X[te])[:, 1]
        lr = make_pipeline(StandardScaler(),
                           LogisticRegression(max_iter=2000,
                                              class_weight="balanced",
                                              random_state=seed)).fit(X[tr], y[tr])
        proba_lr[te] = lr.predict_proba(X[te])[:, 1]
    return proba, proba_lr


def metriques(y, score, nom, seuil=None):
    from sklearn.metrics import roc_auc_score, average_precision_score
    try:
        auc = roc_auc_score(y, score)
        ap = average_precision_score(1 - y, -score)   # détecter les erreurs
    except ValueError:
        return None
    s = seuil if seuil is not None else float(np.median(score))
    escalade = score < s
    erreurs = y == 0
    vp = int((escalade & erreurs).sum())
    fn = int((~escalade & erreurs).sum())
    fp = int((escalade & ~erreurs).sum())
    rappel = vp / max(1, vp + fn)
    precision = vp / max(1, vp + fp)
    print(f"| {nom} | {auc:.3f} | {ap:.3f} | {100*rappel:.1f} % | "
          f"{100*precision:.1f} % | {int(escalade.sum())} |")
    return auc


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--vt", required=True)
    p.add_argument("--ia", required=True)
    p.add_argument("--runs", nargs="*", default=[],
                   help="exécutions répétées du même modèle (stabilité)")
    p.add_argument("--modele2", help="sortie d'un second modèle (accord)")
    p.add_argument("--sources", help="fichier des citations sources, si séparé")
    a = p.parse_args()

    X, y, g, heur, meta = construire(a.vt, a.ia, a.runs, a.modele2, a.sources)
    if len(y) < 30:
        raise SystemExit(f"Corpus trop petit ({len(y)} observations).")

    print(f"Observations : {len(y)}  |  champs corrects : {y.mean()*100:.1f} %"
          f"  |  contrats : {len(set(g))}")
    print(f"Descripteurs : {X.shape[1]}")

    proba, proba_lr = evaluer(X, y, g, heur)

    print(f"\n{'=' * 78}")
    print("PRÉDICTION DE LA FIABILITÉ — modèles appris vs heuristique actuelle")
    print(f"{'=' * 78}")
    print("| Méthode | AUC | AP (erreurs) | Rappel escalade | Précision | Escaladés |")
    print("|---|---|---|---|---|---|")
    metriques(y, heur, "Heuristique à paliers (système actuel)")
    metriques(y, proba_lr, "Régression logistique")
    metriques(y, proba, "Gradient boosting")

    print("\nLecture : l'AUC mesure la capacité à ordonner les champs du moins")
    print("au plus fiable. 0,5 = aucun pouvoir prédictif. Le rappel d'escalade")
    print("est calculé à volume d'escalade égal, seule comparaison équitable.")

    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.inspection import permutation_importance
    clf = HistGradientBoostingClassifier(max_iter=250, max_depth=3,
                                         random_state=0).fit(X, y)
    r = permutation_importance(clf, X, y, n_repeats=8, random_state=0,
                               scoring="roc_auc")
    print("\n--- Descripteurs les plus informatifs ---")
    print("| Descripteur | Importance |")
    print("|---|---|")
    for i in np.argsort(-r.importances_mean)[:10]:
        print(f"| {NOMS[i]} | {r.importances_mean[i]:.4f} |")

    # Champs les plus difficiles à prédire
    print("\n--- Taux de correction observé par champ ---")
    print("| Champ | n | Corrects | Score moyen prédit |")
    print("|---|---|---|---|")
    par_champ = {}
    for (cle, champ), yi, pi in zip(meta, y, proba):
        d = par_champ.setdefault(champ, [0, 0, 0.0])
        d[0] += 1; d[1] += int(yi); d[2] += pi
    for champ, (n, ok, s) in sorted(par_champ.items(), key=lambda x: x[1][1]/max(1,x[1][0])):
        print(f"| {champ} | {n} | {100*ok/n:.0f} % | {100*s/n:.0f} % |")


if __name__ == "__main__":
    main()
