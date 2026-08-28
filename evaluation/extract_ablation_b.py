#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ablation B — « et si on laissait le modèle décider ? »

Ton système demande au modèle de produire lui-même le champ "IFRS 15 AGI"
(champ 11 du prompt), puis apply_ifrs_rules() l'écrase par le résultat de la
règle déterministe. Les deux valeurs existent donc pour chaque dossier :
    - celle du modèle, dans evidence["response_full"] (JSON brut)
    - celle de la règle, dans le résultat post-traité

Ce script récupère la première depuis les traces d'exécution stockées, et
produit la comparaison des deux contre la vérité terrain. AUCUN appel API
n'est nécessaire : la comparaison porte sur des données déjà produites, ce
qui la rend rigoureusement appariée.

PRÉREQUIS
---------
Il faut que les traces (evidence) aient été sauvegardées. Deux cas :

  A. Tu as déjà des fichiers JSON d'evidence sur disque
     -> --traces ./chemin/vers/dossier_traces

  B. Tu ne les as pas sauvegardées
     -> ajoute cette ligne dans real_analyzer.analyze_contract_real(),
        juste après l'appel à aws.analyze_* et AVANT le post-processing :

            import json as _json
            from pathlib import Path as _P
            _d = _P("traces"); _d.mkdir(exist_ok=True)
            (_d / f"{contract_label}.json").write_text(
                _json.dumps({"brut": result, "evidence": evidence},
                            ensure_ascii=False, indent=2), encoding="utf-8")

        puis relance une passe sur ton corpus.

USAGE
-----
    python extract_ablation_b.py --traces ./traces --vt verite_terrain.xlsx
"""

import argparse
import json
import re
from pathlib import Path

import pandas as pd


def norm_bool(v):
    if v is None:
        return None
    s = str(v).strip().lower()
    if s.startswith(("yes", "oui", "y", "true", "1")):
        return "OUI"
    if s.startswith(("no", "non", "n", "false", "0")):
        return "NON"
    return None


def extraire_json(texte):
    """Récupère le bloc structuré dans la réponse brute du modèle."""
    if not texte:
        return None
    # On cherche le plus grand bloc équilibré, plus robuste que la regex
    # à un seul niveau d'imbrication utilisée en production.
    debut = texte.find("{")
    if debut < 0:
        return None
    profondeur = 0
    for i in range(debut, len(texte)):
        if texte[i] == "{":
            profondeur += 1
        elif texte[i] == "}":
            profondeur -= 1
            if profondeur == 0:
                try:
                    return json.loads(texte[debut:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def charger_traces(dossier):
    """Retourne {client: {"modele": decision, "pct_modele": x, "regle": decision}}."""
    out = {}
    for p in sorted(Path(dossier).glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"! illisible : {p.name} ({e})")
            continue

        brut = d.get("brut")
        ev = d.get("evidence", d)
        if brut is None:
            brut = extraire_json(ev.get("response_full", ""))
        if not isinstance(brut, dict):
            print(f"! pas de sortie structurée dans {p.name}")
            continue

        client = brut.get("Client Name") or p.stem
        out[client] = {
            "modele": norm_bool(brut.get("IFRS 15 AGI")),
            "pct_modele": brut.get("Ramp-up price % TCV"),
            "rampup_type": brut.get("Ramp up price"),
            "regle": norm_bool(d.get("post", {}).get("IFRS 15 AGI"))
                     if isinstance(d.get("post"), dict) else None,
            "fichier": p.name,
        }
    return out


def appliquer_regle(t, seuil):
    """Rejoue la règle déterministe hors du système, pour comparaison."""
    typ = (t.get("rampup_type") or "").strip().lower()
    if typ in ("périmètre", "perimetre", "périmetre", "scope", "perimeter"):
        return "OUI"
    try:
        pct = float(t.get("pct_modele") or 0)
    except (TypeError, ValueError):
        pct = 0.0
    return "OUI" if pct < seuil else "NON"


def matrice(paires):
    vc = sum(1 for r, s in paires if r == "OUI" and s == "OUI")
    vn = sum(1 for r, s in paires if r == "NON" and s == "NON")
    fn = sum(1 for r, s in paires if r == "NON" and s == "OUI")
    fp = sum(1 for r, s in paires if r == "OUI" and s == "NON")
    return vc, vn, fp, fn


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--traces", required=True)
    p.add_argument("--vt", required=True)
    p.add_argument("--seuil", type=float, default=10.0,
                   help="seuil AGI utilisé en production")
    p.add_argument("--col-client", default="Client Name")
    p.add_argument("--col-decision", default="IFRS 15 AGI")
    a = p.parse_args()

    traces = charger_traces(a.traces)
    print(f"Traces chargées : {len(traces)} dossiers")

    vt = pd.read_excel(a.vt) if a.vt.endswith((".xlsx", ".xls")) \
        else pd.read_csv(a.vt)
    vt.columns = [str(c).strip() for c in vt.columns]

    ref = {}
    for _, row in vt.iterrows():
        c = str(row.get(a.col_client, "")).strip()
        if c:
            ref[c.lower()] = norm_bool(row.get(a.col_decision))

    paires_b, paires_a, manquants = [], [], []
    lignes = []
    for client, t in traces.items():
        r = ref.get(str(client).strip().lower())
        if r is None:
            manquants.append(client)
            continue
        dec_modele = t["modele"]
        dec_regle = t["regle"] or appliquer_regle(t, a.seuil)
        if dec_modele:
            paires_b.append((r, dec_modele))
        if dec_regle:
            paires_a.append((r, dec_regle))
        lignes.append((client, r, dec_modele, dec_regle,
                       "=" if dec_modele == dec_regle else "DIVERGENT"))

    if manquants:
        print(f"! {len(manquants)} dossiers sans correspondance dans la vérité "
              f"terrain : {', '.join(manquants[:5])}...")

    for nom, paires in (("A — Règle déterministe", paires_a),
                        ("B — Décision du modèle", paires_b)):
        if not paires:
            continue
        vc, vn, fp, fn = matrice(paires)
        tot = len(paires)
        print(f"\n=== Configuration {nom} ({tot} dossiers) ===")
        print("|                        | Réf. conforme | Réf. non conforme |")
        print("|------------------------|---------------|-------------------|")
        print(f"| Système : conforme     | {vc} | {fn} (faux négatifs) |")
        print(f"| Système : non conforme | {fp} (faux positifs) | {vn} |")
        print(f"Concordance : {vc+vn}/{tot} ({100*(vc+vn)/tot:.1f} %)")
        print(f"Faux négatifs : {fn}  <- erreur la plus coûteuse")

    div = [l for l in lignes if l[4] == "DIVERGENT"]
    print(f"\n=== Dossiers où modèle et règle divergent : {len(div)} ===")
    for c, r, dm, dr, _ in div:
        gagnant = "règle" if dr == r else ("modèle" if dm == r else "aucun")
        print(f"  {c} : réf={r}, modèle={dm}, règle={dr}  -> {gagnant} a raison")

    print("\nCes divergences sont la matière première du §6.3 du mémoire :")
    print("elles isolent l'apport propre de la couche déterministe.")


if __name__ == "__main__":
    main()
