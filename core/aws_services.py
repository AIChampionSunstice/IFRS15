import boto3
import json
import time
from pathlib import Path
from typing import Dict, Tuple
import streamlit as st
from datetime import datetime

class AWSServices:
    def __init__(self):
        region = st.secrets['aws']['region']
        self.bucket_name = st.secrets['aws']['bucket_name']
        aws_access_key = st.secrets['aws']['access_key_id']
        aws_secret_key = st.secrets['aws']['secret_access_key']
        
        self.s3_client = boto3.client(
            's3',
            region_name=region,
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key
        )
        
        self.textract_client = boto3.client(
            'textract',
            region_name=region,
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key
        )
        
        self.bedrock_client = boto3.client(
            'bedrock-runtime',
            region_name=region,
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key
        )
        
        self.model_id = 'global.anthropic.claude-opus-4-6-v1'
        
    def upload_to_s3(self, file_path: Path, s3_key: str) -> str:
        try:
            with open(file_path, 'rb') as f:
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=f
                )
            return f"s3://{self.bucket_name}/{s3_key}"
        except Exception as e:
            raise Exception(f"Erreur upload S3: {str(e)}")
    
    def extract_text_with_textract(self, s3_key: str) -> str:
        
        try:
            response = self.textract_client.start_document_analysis(
                DocumentLocation={
                    'S3Object': {
                        'Bucket': self.bucket_name,
                        'Name': s3_key
                    }
                },
                FeatureTypes=['TABLES']
            )
            
            job_id = response['JobId']
            max_wait = 300
            waited = 0
            
            while waited < max_wait:
                result = self.textract_client.get_document_analysis(JobId=job_id)
                status = result['JobStatus']
                
                if status == 'SUCCEEDED':
                    break
                elif status == 'FAILED':
                    raise Exception("Textract a échoué")
                
                time.sleep(5)
                waited += 5
            
            if status != 'SUCCEEDED':
                raise Exception(f"Textract timeout après {max_wait}s")

            text = ""

            all_blocks = result.get('Blocks', [])
            next_token = result.get('NextToken')
            
            while next_token:
                result = self.textract_client.get_document_analysis(
                    JobId=job_id,
                    NextToken=next_token
                )
                all_blocks.extend(result.get('Blocks', []))
                next_token = result.get('NextToken')
            
            for block in all_blocks:
                if block['BlockType'] == 'LINE':
                    text += block['Text'] + "\n"
            
            table_blocks = [b for b in all_blocks if b['BlockType'] == 'TABLE']
            
            for table_block in table_blocks:
                table_text = "TABLEAU DÉTECTÉ"
                
                if 'Relationships' in table_block:
                    for relationship in table_block['Relationships']:
                        if relationship['Type'] == 'CHILD':
                            cells = []
                            for cell_id in relationship['Ids']:
                                cell_block = next((b for b in all_blocks if b['Id'] == cell_id), None)
                                if cell_block and cell_block['BlockType'] == 'CELL':
                                    cell_text = ""
                                    if 'Relationships' in cell_block:
                                        for cell_rel in cell_block['Relationships']:
                                            if cell_rel['Type'] == 'CHILD':
                                                for word_id in cell_rel['Ids']:
                                                    word_block = next((b for b in all_blocks if b['Id'] == word_id), None)
                                                    if word_block and 'Text' in word_block:
                                                        cell_text += word_block['Text'] + " "
                                    
                                    row = cell_block.get('RowIndex', 0)
                                    col = cell_block.get('ColumnIndex', 0)
                                    cells.append((row, col, cell_text.strip()))
                    
                            if cells:
                                max_row = max(c[0] for c in cells)
                                max_col = max(c[1] for c in cells)
                                
                                for row in range(1, max_row + 1):
                                    row_cells = [c for c in cells if c[0] == row]
                                    row_cells.sort(key=lambda x: x[1])
                                    table_text += " | ".join(c[2] for c in row_cells) + "\n"
                
                text += table_text
            
            return text
            
        except Exception as e:
            raise Exception(f"Erreur Textract: {str(e)}")
    
    def classify_document_type(self, text: str) -> str:
        text_upper = text.upper()
        
        if "MASTER SERVICES AGREEMENT" in text_upper or "MASTER SERVICE AGREEMENT" in text_upper:
            return "Master Agreement"
        elif "SAAS" in text_upper and "AGREEMENT" in text_upper:
            return "SaaS Agreement"
        elif "ORDER FORM" in text_upper:
            return "Order Form"
        elif "SCHEDULE A" in text_upper or "ADDENDUM" in text_upper:
            return "Addendum"
        else:
            return "Unknown"
    
    def _extract_date_from_master_agreement(self, texts_dict: Dict[str, str]) -> str:
        master_text = None
        for doc_type, text in texts_dict.items():
            if "master" in doc_type.lower() and "agreement" in doc_type.lower():
                master_text = text
                break
        
        if not master_text:
            return None
        
        import re

        match = re.search(r'Dated\s+(\d{1,2})[-/](\d{1,2})[-/](\d{4})', master_text, re.IGNORECASE)
        if match:
            day, month, year = match.groups()
            return f"{day.zfill(2)}/{month.zfill(2)}/{year}"
        
        # Pattern "Dated DD-month-YYYY"
        match = re.search(r'Dated\s+(\d{1,2})[-\s](\w+)[-\s](\d{4})', master_text, re.IGNORECASE)
        if match:
            day, month_name, year = match.groups()
            
            month_map = {
                'jan': '01', 'january': '01', 'janvier': '01',
                'feb': '02', 'february': '02', 'février': '02', 'fev': '02',
                'mar': '03', 'march': '03', 'mars': '03',
                'apr': '04', 'april': '04', 'avril': '04', 'avr': '04',
                'may': '05', 'mai': '05',
                'jun': '06', 'june': '06', 'juin': '06',
                'jul': '07', 'july': '07', 'juillet': '07',
                'aug': '08', 'august': '08', 'août': '08', 'aout': '08',
                'sep': '09', 'september': '09', 'septembre': '09', 'sept': '09',
                'oct': '10', 'october': '10', 'octobre': '10',
                'nov': '11', 'november': '11', 'novembre': '11',
                'dec': '12', 'december': '12', 'décembre': '12', 'decembre': '12'
            }
            
            month_num = month_map.get(month_name.lower()[:3])
            if month_num:
                return f"{day.zfill(2)}/{month_num}/{year}"
        
        return None
    
    def _build_multi_doc_context(self, texts_dict: Dict[str, str]) -> str:
        
        context = "═══════════════════════════════════════════════════════════════════\n"
        context += " ATTENTION : ANALYSE MULTI-DOCUMENTS D'UN SEUL CLIENT\n"
        context += "═══════════════════════════════════════════════════════════════════\n\n"
        context += "Tu analyses PLUSIEURS documents du MÊME client. Ne confonds JAMAIS les informations entre documents.\n\n"
        
        for doc_type, text in texts_dict.items():
            text_truncated = text[:50000] if len(text) > 50000 else text
            
            context += f"DOCUMENT: {doc_type.upper()} ▼▼▼\n"
            context += f"(Longueur: {len(text)} caractères)\n\n"
            context += text_truncated
            context += f"\n\nFIN {doc_type.upper()} ▲▲▲\n\n"
            context += "─" * 70 + "\n\n"
        
        return context
    
    def _get_base_prompt(self, text_chunk: str, agi_threshold: float, client_name: str) -> str:       
        return f"""Tu es un expert comptable IFRS15 spécialisé dans les contrats SaaS FuturMaster.

CONTRAT À ANALYSER:
{text_chunk}

═══════════════════════════════════════════════════════════════════
 RÈGLE ANTI-HALLUCINATION - ABSOLUMENT CRITIQUE
═══════════════════════════════════════════════════════════════════

**SI TU NE TROUVES PAS L'INFORMATION AVEC CERTITUDE DANS LE CONTRAT :**

 NE JAMAIS inventer, supposer, déduire, ou extrapoler
 TOUJOURS mettre : "Not found"

**NIVEAU DE CERTITUDE REQUIS :**
- **95%+ de confiance** avec citation exacte du contrat → Indiquer la valeur
- **< 95% de confiance** → "Not found"

**Exemples de cas "NOT FOUND" :**

 MAUVAIS :
Date non trouvée → Inventer "01/02/2025" ou utiliser "Effective Date" comme substitut
 BON :
Date non trouvée → "Not found"

 MAUVAIS :
Durée non mentionnée → Supposer "3 ans" car c'est standard
 BON :
Durée non mentionnée → "Not found"

 MAUVAIS :
Setup fees ambigus → Mettre un montant "probable"
 BON :
Setup fees ambigus → Setup fees = "No", Setup fees € = 0

**Champs où "Not found" est AUTORISÉ :**
- Date signature
- SaaS Start Date
- End date théorique
- Option Sortie
- Start date ignition
- Durée du Contrat (si vraiment introuvable)

**Champs où mettre valeur par défaut (JAMAIS "Not found") :**
- Setup fees € → 0
- Ramp up price impact € vs TCV → 0
- Ramp-up price % TCV → 0
- Price Ramp-up → "No" (si aucune méthode ne détecte de ramp-up)

═══════════════════════════════════════════════════════════════════
 RÈGLE CRITIQUE - CALCUL TCV RAMP-UP
═══════════════════════════════════════════════════════════════════

** ATTENTION : Ne JAMAIS confondre les montants mensuels avec l'écart TCV !**

**ERREUR FRÉQUENTE À ÉVITER :**
 BAD : "Phase 2 : 4500€/mois" → Retourner 4500 comme écart
 GOOD : Calculer : TCV théorique - TCV réel = Écart

**EXEMPLE PÉDAGOGIQUE (montants fictifs Entreprise ABC) :**
```
Contrat fictif:
Phase 1 (mois 1-12) : 10,000€/mois
Phase 2 (mois 13-36) : 9,500€/mois
Durée totale : 36 mois
```

**CALCUL CORRECT :**

**Étape 1 : MRR standard (prix plein)**
→ MRR standard = 10,000€/mois (le plus élevé)

**Étape 2 : TCV théorique**
→ TCV théorique = 10,000 × 36 = 360,000€

**Étape 3 : TCV réel**
→ Phase 1 : 10,000 × 12 = 120,000€
→ Phase 2 : 9,500 × 24 = 228,000€
→ TCV réel = 120,000 + 228,000 = 348,000€

**Étape 4 : Écart (RÉPONSE FINALE)**
→ Écart = 360,000 - 348,000 = **12,000€**

**→ RETOURNE : 12000** (PAS 9500 !)

═══════════════════════════════════════════════════════════════════
RÈGLES DE DÉTECTION GÉNÉRALES
═══════════════════════════════════════════════════════════════════

**DÉTECTION Yes/No/Oui:**
- **YES** = Yes, yes, YES, Y, y, Oui, oui, OUI, ✓, ✔, ☑, ☒, X, [X], [x], (X), (x), Checked, True, 1
- **NO** = No, no, NO, N, n, Non, non, NON, ☐, [ ], Unchecked, False, 0

**DÉTECTION DATES:**
- TOUJOURS convertir au format DD/MM/YYYY
- Si date pas trouvée avec CERTITUDE → "Not found"
- Exemples de conversions:
  * "13-févr.-2025" → "13/02/2025"
  * "19-nov.-2025" → "19/11/2025"
  * "29-janv.-2024" → "29/01/2024"
  * "February 13, 2025" → "13/02/2025"
  * "2025-02-13" → "13/02/2025"

**TABLE DE CONVERSION MOIS :**
jan/january/janvier=01, fév/feb/february/février=02, mar/march/mars=03, 
avr/apr/april/avril=04, mai/may=05, juin/jun/june=06, 
juil/jul/july/juillet=07, août/aug/august=08, sep/september/septembre=09, 
oct/october/octobre=10, nov/november/novembre=11, déc/dec/december/décembre=12

**DÉTECTION MONTANTS:**
- Reconnais: 5000€, €5000, 5,000€, 5.000€, EUR 5000, 5000 euros
- Convertis toujours en nombre: 5000
- Si "K" → multiplie par 1000 (ex: 5K → 5000)

═══════════════════════════════════════════════════════════════════
CHAMPS À EXTRAIRE (1-8 : STANDARD)
═══════════════════════════════════════════════════════════════════

**1. CLIENT NAME**
- Source prioritaire: Nom du fichier → {client_name}
- Source secondaire: Dans le contrat (en-tête, "Customer:", "Client:")
- Retourne le nom complet de l'entreprise

**2. TYPE DE CONTRAT**
- Cherche: "SaaS", "Cloud Services", "Subscription", "On-Premise", "Hybrid"
- Variantes à reconnaître:
  * "SaaS FM Cloud Services Agreement" → "SaaS"
  * "Cloud Subscription" → "SaaS"
  * "Software as a Service" → "SaaS"
- Par défaut si non trouvé: "SaaS"

**3. CONTRAT FORMAT SUNSTICE (Yes/No)**
- **INDICES FORMAT SUNSTICE:**
  1. Mention "FuturMaster SaaS FM Cloud Services Agreement"
  2. Titres avec traits bleus horizontaux (─────)
  3. Structure: "Article X - [Titre]" avec trait bleu dessous
  4. Sections: "General Terms and Conditions", "Definitions and Interpretation"
  
- **DÉTECTION:**
  * Si 2+ indices présents → "Yes"
  * Si structure différente → "No"

**4. DATE SIGNATURE (DD/MM/YYYY) - DÉTECTION DOCUSIGN PRIORITAIRE**

**PRIORITÉ ABSOLUE : Chercher après "DocuSigned by:"**

**Pattern DocuSign (le plus fréquent) :**
DocuSigned by:
[Nom Prénom] [Signature manuscrite/image]
Date: 19-nov.-2025 | 09:41:57 CET

**Instructions de détection :**
1. Cherche d'abord le mot "DocuSigned by:" (case insensitive)
2. Les 3-5 lignes APRÈS contiennent généralement la date
3. La date est souvent au format : "DD-mois-YYYY | HH:MM:SS TIMEZONE"
4. Extraire UNIQUEMENT la partie date (avant le "|")

**Exemples réels :**
- "19-nov.-2025 | 09:41:57 CET" → "19/11/2025"
- "29-janv.-2024 | 14:23:10 CET" → "29/01/2024"
- "13-février-2025" → "13/02/2025"

**Emplacements alternatifs (si DocuSign pas trouvé) :**
1. "Fait à [ville], le [date]"
2. En bas du contrat, zone signatures
3. Champ "Date:" ou "Signed on:"
4. "Effective Date:" (en dernier recours)

**CONVERSION OBLIGATOIRE :**
- Mois en lettres → nombres (utilise TABLE DE CONVERSION ci-dessus)
- Format final: DD/MM/YYYY

**Si AUCUNE date trouvée avec certitude → "Not found"**

**5. SCOPE (Demand, Supply, TPX, SCH)**
- **VARIANTES À RECONNAÎTRE:**
  * Demand = Demande, Demand Planning, DP, FM Demand, Demand Management
  * Supply = Supply Planning, Supply Chain, SP, FM Supply, Optimized Supply Planning
  * TPX = Trade Promotion, TPX, Trade Promo, Trade Promotion Management
  * SCH = Scheduling, Schedule

- **DÉTECTION:**
  * Cherche dans tableaux de prix (colonne "Service")
  * Cherche "Modules:", "Scope:", "Périmètre:"
  * Peut être multiple: "Demand, Supply"
  * Si "FM Demand Planning" trouvé → Inclure "Demand"
  * Si "FM Supply Planning" trouvé → Inclure "Supply"

**6. DURÉE DU CONTRAT**
- **VARIANTES:**
  * "36 mois" → "36 mois"
  * "3 ans" → "3 ans"
  * "three years" → "3 ans"
  * "12 months" → "12 mois"
  * "period of 3 (three) years" → "3 ans"

- **NORMALISATION:**
  * Toujours préciser l'unité (mois ou ans)

- **Si pas trouvée avec certitude → "Not found"**

**7. PRICE RAMP-UP (Yes/No) - DÉTECTION MULTI-MÉTHODES**

**MÉTHODE 1 : Tableaux multiples de prix**
Si tu trouves PLUSIEURS tableaux avec titres différents :
- "Year 1 Pricing" / "Année 1"
- "Year 2-3 Pricing" / "Années 2-3"
- "Phase 1" / "Phase 2"
→ Ramp-up = Yes

**MÉTHODE 2 : Prix différents par période dans le texte**
Cherche patterns comme :
- "Months 1-12: XXX€"
- "Months 13-36: YYY€"
- "First year: XXX€"
- "Subsequent years: YYY€"
Si XXX ≠ YYY → Ramp-up = Yes

**MÉTHODE 3 : Mots-clés de variation tarifaire**
Cherche (case insensitive) :
- "commercial gesture" / "geste commercial"
- "promotional price" / "tarif promotionnel"
- "discount first year" / "remise première année"
- "introductory pricing" / "special pricing"
- "ramp-up" suivi d'une période (ex: "ramp-up du 01/01/2026 au 30/06/2027")
- "montée en charge" / "facturation progressive"
Si trouvé → Ramp-up = Yes

**MÉTHODE 4 : Scope progressif**
Si tu vois des modules ou utilisateurs qui s'ajoutent entre périodes :
- "Phase 1: Demand only" puis "Phase 2: Demand + Supply"
- Ajout de modules entre périodes
→ Ramp-up = Yes

**MÉTHODE 5 : Analyse des tableaux**
Compare les montants "Total Monthly Price" entre différents tableaux
Si différence > 5% → Ramp-up = Yes

**MÉTHODE 6 : Calendrier de facturation progressif**
Si les montants facturés augmentent d'année en année et se stabilisent :
- Année 1 : montant X (inférieur)
- Année 2 : montant Y (intermédiaire)
- Années suivantes : montant Z (stable = prix plein)
→ Ramp-up = Yes

**RÈGLE CRITIQUE - Distinction remise totale vs partielle :**

**CAS 1 : Remise sur TOUTE la durée → PAS de ramp-up IFRS15**
La même remise apparaît dans CHAQUE tableau/période du contrat.
→ Ramp-up = No

**CAS 2 : Remise PARTIELLE sur certaines périodes seulement → Ramp-up IFRS15**
La remise disparaît à un moment → prix augmente.
→ Ramp-up = Yes

**Si AUCUNE méthode ne détecte de ramp-up :**
→ Ramp-up = No

**8. RAMP UP PRICE (Commercial / Périmètre / Périmètre + Commercial / TBD)**

═══════════════════════════════════════════════════════════════════
PRINCIPE FONDAMENTAL — RAISONNEMENT EN 2 QUESTIONS INDÉPENDANTES
═══════════════════════════════════════════════════════════════════

Tu dois répondre à deux questions indépendantes, puis combiner les réponses.

**QUESTION A — Y a-t-il un ramp-up COMMERCIAL ?**
→ "Le prix payé par le client pour un périmètre identique augmente-t-il
   au cours du contrat ?"

Si oui → composante COMMERCIAL présente.

La forme importe peu : remise sur premiers mois, prix progressif dans
un calendrier de facturation, discount conditionnel qui disparaît,
période de ramp-up explicite avec dates… Le seul critère qui compte :
**même scope, prix différent selon la période.**

**QUESTION B — Y a-t-il un ramp-up PÉRIMÈTRE ?**
→ "Le périmètre contractuel (modules, utilisateurs, services) s'étend-il
   progressivement au cours du contrat ?"

Si oui → composante PÉRIMÈTRE présente.

Critère clé : Phase 2 **contient** Phase 1 + davantage (extension).
Ce n'est PAS du périmètre si Phase 2 **remplace** Phase 1
(ex : Demand → Supply seul = remplacement, pas extension).

**RÈGLE DE COMBINAISON :**
- Question A = Oui, Question B = Non → "Commercial"
- Question A = Non, Question B = Oui → "Périmètre"
- Question A = Oui, Question B = Oui → "Périmètre + Commercial"
- Ramp-up détecté mais raison indéterminable → "TBD"

═══════════════════════════════════════════════════════════════════
PIÈGE CRITIQUE — REMISE UNIFORME ≠ RAMP-UP COMMERCIAL
═══════════════════════════════════════════════════════════════════

**Une remise négociée appliquée sur TOUTE la durée du contrat
n'est PAS un ramp-up commercial IFRS15.**

Pourquoi : le prix contractuel est constant. Il n'y a aucune variation
de tarification dans le temps.

**Comment distinguer :**
- Remise uniforme : le même % apparaît dans chaque période/tableau
  (Year 1, Year 2, Year 3… tous à -20%) → réponse Question A = NON
- Remise partielle : le % ne s'applique qu'à certaines périodes
  puis disparaît → réponse Question A = OUI

═══════════════════════════════════════════════════════════════════
EXEMPLES RÉELS — RAISONNEMENT ATTENDU
═══════════════════════════════════════════════════════════════════

**EXEMPLE 1 — Commercial pur (facturation progressive sur premiers mois)**

Extrait :
"Le montant des trois premiers loyers sera de 50% du montant total
puis 75% du montant total les deux mois suivants."
MRR standard : 12 000€/mois. Durée : 5 ans.

Raisonnement :
- Question A : même scope, mois 1-3 à 6 000€, mois 4-5 à 9 000€,
  mois 6-60 à 12 000€. Prix augmente jusqu'au plein. → OUI commercial
- Question B : aucun changement de modules ni d'utilisateurs. → NON périmètre
→ "Commercial"

---

**EXEMPLE 2 — Commercial pur (calendrier de facturation progressif)**

Extrait :
"la remise commerciale de 16% ne sera plus pratiquée sur les factures suivantes"
Calendrier :
- 01/09/2021 : 35 750€
- 01/01/2022 : 89 620€
- 01/01/2023 : 129 578€
- 01/01/2024 : 131 695€ (stable = prix plein)

Raisonnement :
- Question A : montants croissants puis stables. Remise qui disparaît
  progressivement. Même scope tout au long. → OUI commercial
- Question B : un seul tableau de services, pas de phases de modules. → NON périmètre
→ "Commercial"

---

**EXEMPLE 3 — Commercial pur (période de ramp-up explicite avec dates)**

Extrait :
"Prix mensuel (HT) : 10 670€
Offre client : 8 204€/mois
Ramp-up du 31/12/2025 au 30/06/2027 : 6 500€/mois
À partir du 01/07/2027 : 8 204€/mois"

Raisonnement :
- Question A : prix réduit (6 500€) pendant une période bornée,
  retour au prix négocié (8 204€) ensuite. → OUI commercial
- Question B : aucun ajout de module ou d'utilisateurs décrit. → NON périmètre
→ "Commercial"

---

**EXEMPLE 4 — Périmètre pur (augmentation d'utilisateurs, remise uniforme)**

Extrait :
Tableau Année 1 : Collaborative Users = 6, Viewer = 4 → Total 6 752€/mois
  Note : "remise exceptionnelle de 20% pour décision février 2024"
Tableau Année 2 : Collaborative Users = 9, Viewer = 6 → Total 8 648€/mois
  Note : "remise exceptionnelle de 20% pour décision février 2024"
Tableau Run : même note remise 20% → Total 11 744€/mois

Raisonnement :
- Question A : la remise 20% est présente dans TOUS les tableaux
  (Année 1, Année 2 ET Run). Le prix varie uniquement parce que le nombre
  d'utilisateurs varie, pas parce qu'une remise disparaît.
  → NON commercial (remise uniforme sur toute la durée)
- Question B : Collaborative 6→9, Viewer 4→6 entre Année 1 et Année 2.
  Plus d'utilisateurs en Phase 2 qu'en Phase 1. Extension progressive. → OUI périmètre
→ "Périmètre"

---

**EXEMPLE 5 — Périmètre pur (déploiement en phases de modules)**

Extrait :
"Le projet se déroulera en 2 phases :
Phase 1 : FM Demand Management → 5 875€/mois
Phase 2 : FM Optimized Planning → 5 795€/mois"

Raisonnement :
- Question A : prix quasi identiques (5 875 vs 5 795€), pas de remise
  mentionnée. Variation marginale ne reflète pas une remise commerciale. → NON commercial
- Question B : deux phases de déploiement avec modules différents dans
  le cadre d'un projet progressif. Phase 2 s'ajoute à Phase 1
  (ou étend le déploiement). → OUI périmètre
→ "Périmètre"

  ATTENTION : Si Phase 2 remplaçait totalement Phase 1 sans continuité
  (ex: abandon de Demand, démarrage Supply seul), ce serait un remplacement,
  pas une extension → NON périmètre dans ce cas.

---

**EXEMPLE 6 — Périmètre + Commercial (cas mixte)**

Extrait :
"Geste commercial : -40% mois 1-2.
Phase 1 (mois 1-12) : FM Demand - 5 utilisateurs
Phase 2 (mois 13-36) : FM Demand + FM Supply - 10 utilisateurs"

Raisonnement :
- Question A : remise -40% sur les 2 premiers mois seulement.
  Prix augmente ensuite (remise disparaît). → OUI commercial
- Question B : Supply ajouté en Phase 2, utilisateurs doublent (5→10).
  Extension du périmètre. → OUI périmètre
→ "Périmètre + Commercial"

---

**EXEMPLE 7 — TBD (variation constatée, cause indéterminable)**

Extrait :
"Montant total : 270 100€ sur 3 ans et 1 mois
- 01/12/2019 : 153 360€
- 01/12/2020 : 54 720€
- 01/12/2021 : 62 020€"

Raisonnement :
- Question A : montants très variables (153k → 54k → 62k) mais aucune
  clause n'explique cette variation. Première facture anormalement haute
  (peut inclure du one-time). Tendance non linéaire impossible à interpréter.
  → Impossible de conclure
- Question B : un seul tableau de services visible, pas de phases décrites.
  → NON périmètre
→ "TBD" (variation constatée, raison indéterminée avec certitude)

═══════════════════════════════════════════════════════════════════
RÈGLES DE DÉCISION FINALES
═══════════════════════════════════════════════════════════════════

1. **Toujours raisonner en deux temps** : Question A puis Question B,
   de façon indépendante.

2. **La forme contractuelle ne détermine pas la classification.**
   Calendrier de facturation, tableaux multi-périodes, clause textuelle,
   % de remise : raisonne toujours sur l'effet économique.
   Le prix pour un scope donné varie-t-il dans le temps ?

3. **Remise uniforme sur toute la durée = réponse A est NON.**
   Vérifie si la remise apparaît dans TOUTES les périodes/tableaux.

4. **Extension de périmètre = addition, pas remplacement.**
   Phase 2 = Phase 1 + X → OUI périmètre.
   Phase 2 = X seulement → NON périmètre.

5. **En cas de doute réel → "TBD"** plutôt qu'une classification incorrecte.

6. **Traçabilité obligatoire dans "sources" :**
   Indique les réponses aux deux questions avec citations exactes.
   Format : "Q.A → [OUI/NON + justification courte]. Q.B → [OUI/NON + justification]. → [valeur]"

═══════════════════════════════════════════════════════════════════
 CHAMPS 9-10 : CALCUL TCV RAMP-UP (CRITIQUE)
═══════════════════════════════════════════════════════════════════

**9. RAMP UP PRICE IMPACT € VS TCV - MÉTHODE ULTRA PRÉCISE**

** OBJECTIF : Calculer l'ÉCART entre TCV théorique et TCV réel**

** MÉTHODE ÉTAPE PAR ÉTAPE :**

**ÉTAPE 1 : Identifier le MRR STANDARD (prix plein)**

Cherche dans le contrat :
- Tableau avec "Standard pricing" ou "Full price"
- Prix des années 2-3 (si ramp-up Année 1 seulement)
- Tableau SANS mention "promotional" ou "Year 1 only"

**Dans les tableaux, cherche :**
Colonnes : "Monthly Unit Price" ou "Total Monthly Price"

**Calcul MRR standard :**
MRR standard = SOMME de tous les "Total Monthly Price" du tableau standard

Exemple tableau fictif :
| Service | Quantity | Monthly Unit Price | Total Monthly Price |
| Module A | 1 | 2000€ | 2000€ |
| Module B | 1 | 1500€ | 1500€ |
| Module C | 5 | 400€ | 2000€ |

MRR standard = 2000 + 1500 + 2000 = 5,500€/mois

**Si plusieurs tableaux :**
→ MRR standard = Prix le PLUS ÉLEVÉ trouvé

**ÉTAPE 2 : Calculer TCV THÉORIQUE**

TCV théorique = MRR standard × Durée totale (mois)

** CONVERSION DURÉE :**
- Si "3 ans" → 36 mois
- Si "5 ans" → 60 mois
- Si "36 mois" → 36 mois

Exemple :
MRR standard = 5,500€/mois
Durée = 3 ans = 36 mois
TCV théorique = 5,500 × 36 = 198,000€

**ÉTAPE 3 : Calculer TCV RÉEL**

Additionne TOUS les paiements RÉELS période par période.

**Si ramp-up détecté :**

Exemple avec pricing différent :
- Année 1 (mois 1-12) : 4,500€/mois = 54,000€
- Années 2-3 (mois 13-36) : 5,500€/mois = 132,000€
TCV réel = 54,000 + 132,000 = 186,000€

**Si facturation annuelle avec calendrier :**
Additionne directement les montants du calendrier de facturation.
TCV réel = somme de toutes les factures

**Si PAS de ramp-up :**
TCV réel = TCV théorique

**ÉTAPE 4 : Calculer l'écart**

Écart = TCV théorique - TCV réel

**→ RETOURNE uniquement le nombre (ex: 12000)**

** VÉRIFICATIONS FINALES :**
1.  L'écart ne peut PAS être un montant mensuel (4500, 5500, etc.)
2.  L'écart ne peut PAS être supérieur au TCV théorique
3.  L'écart doit représenter la "remise totale" sur toute la durée
4.  Si pas de ramp-up → Écart = 0

**CAS SPÉCIAUX IMPORTANTS :**

**CAS A : Pas de ramp-up détecté**
→ Écart = 0

**CAS B : Ramp-up UNIQUEMENT Périmètre (sans remise)**
Si "Ramp up price" = "Périmètre" (SANS "Commercial")
→ Écart = 0 (changement de scope ne compte pas comme remise)

**CAS C : Ramp-up Commercial OU Mixte**
→ Calculer normalement l'écart
→ L'écart reflète UNIQUEMENT la composante remise commerciale

**CAS D : Ramp-up progressif sur premiers mois (ex: 50% puis 75%)**

```
Contrat 5 ans (60 mois), MRR standard = 10,000€/mois
"Les 3 premiers loyers à 50%, puis 75% les 2 mois suivants"

TCV théorique = 10,000 × 60 = 600,000€
TCV réel :
- Mois 1-3 : 5,000 × 3 = 15,000€
- Mois 4-5 : 7,500 × 2 = 15,000€
- Mois 6-60 : 10,000 × 55 = 550,000€
TCV réel = 580,000€
Écart = 20,000€ → % = 3.33%
```

**CAS E : Remise uniforme sur TOUT le contrat**
Prix CONSTANT (même avec remise négociée) = PAS de ramp-up IFRS15
→ Écart = 0

**10. RAMP-UP PRICE % TCV**

**FORMULE : % = (Écart € / TCV théorique) × 100**

**CAS SPÉCIAUX :**
- "Ramp up price" = "Périmètre" seul → % = 0
- "Price Ramp-up" = No → % = 0

═══════════════════════════════════════════════════════════════════
CHAMPS 11-17 : STANDARD
═══════════════════════════════════════════════════════════════════

**11. IFRS 15 AGI (Yes/No)**
- **RÈGLE:**
  - Si Ramp-up % < {agi_threshold}% → "Yes" (conforme)
  - Si Ramp-up % ≥ {agi_threshold}% → "No" (non conforme)
  
  **Exemple avec seuil 10%:**
  - 6.06% < 10% → "Yes"
  - 11.11% ≥ 10% → "No"

**12. OPTION SORTIE AVANT TERME DU CONTRAT**
- **CHERCHE CES CLAUSES:**
  1. "résiliation anticipée"
  2. "résiliation moyennant préavis de X mois"
  3. "résiliation à la convenance du client"
  4. "résiliation pour motif légitime"
  5. "résiliation sans pénalité"
  6. "clause de sortie"
  7. "termination clause"
  8. "early termination"

- **FORMAT RÉPONSE:**
  - Résume en 1-2 phrases
  - Inclus conditions (préavis, pénalités, etc.)

- **Si pas trouvé → "Not found"**

**13. SAAS START DATE (DD/MM/YYYY)**
- **CHERCHE:**
  1. "Le Contrat entrera en vigueur à compter de [date]"
  2. "Effective Date: [date]"
  3. "Start Date: [date]"
  4. "Date de début: [date]"
  5. "The contract starts on [date]"
  6. "Services commence on [date]"

- **SI NON SPÉCIFIÉ:**
  - Si Date signature trouvée → Copier Date signature
  - Sinon → "Not found"

- **FORMAT:** DD/MM/YYYY

**14. START DATE IGNITION**
- **C'EST LA DATE DE DÉBUT DE FACTURATION ARR**

- **CHERCHE:**
  1. "ARR commence après Design"
  2. "Facturation débute après go-live"
  3. "Licence active après implémentation"
  4. "Start billing after [événement]"
  5. "Invoice starts after [événement]"
  6. "Payment begins [date]"

- **RÉPONSES POSSIBLES:**
  - Si date précise → "DD/MM/YYYY"
  - Si après événement → "Start after Design" OU "Start after Implementation" OU "Start after Go-Live"
  - Si = Date SaaS Start → Copier la même date
  - Si pas trouvé → "Not found"

**15. END DATE THÉORIQUE (DD/MM/YYYY)**
- **CALCUL:**
  - Prends SaaS Start Date
  - Ajoute la Durée du contrat
  - Soustraire 1 jour du résultat final
  
  **Exemple:**
  - SaaS Start: 01/02/2024
  - Durée: 36 mois
  - End: 31/01/2027

- **Si SaaS Start ou Durée manquant → "Not found"**

- **FORMAT:** DD/MM/YYYY

**16. SETUP FEES (Yes/No) - DÉTECTION EXHAUSTIVE**

**SECTIONS À SCANNER :**
1. "Professional Services"
2. "One-time Fees"
3. "Project Costs"
4. "Onboarding & Training"
5. Tableaux avec "Non-recurring" ou "One-time"

**MOTS-CLÉS À CHERCHER :**
Formation, Training, Onboarding, Setup fees, Installation,
Configuration, Paramétrage, Integration, Kick-off,
Consulting (si lié au setup)

**SI TROUVÉ au moins un de ces éléments → Setup fees = Yes**
**SI RIEN trouvé → Setup fees = No**

**17. SETUP FEES €**
- **EXTRACTION:**
  1. Cherche montant à côté des mots-clés setup
  2. Si plusieurs lignes → ADDITIONNE
  
- Si aucun montant trouvé → 0

═══════════════════════════════════════════════════════════════════
INSTRUCTIONS SPÉCIALES - TABLEAUX
═══════════════════════════════════════════════════════════════════

**LES CONTRATS FUTURMASTER CONTIENNENT DES TABLEAUX STRUCTURÉS**

**Format type :**
```
=== TABLEAU DÉTECTÉ ===
Service | Quantity | Monthly Unit Price | Total Monthly Price
Module A | 1 | 2000€ | 2000€
Module B | 1 | 1500€ | 1500€
```

**INSTRUCTIONS :**
1. Identifie TOUS les montants dans colonnes "Monthly Unit Price" et "Total Monthly Price"
2. Additionne les "Total Monthly Price" pour obtenir le MRR
3. Si plusieurs tableaux avec périodes différentes → RAMP-UP
4. Cherche aussi "Annual Fee", "Yearly Price", "Prix total/AN" pour prix annuel

═══════════════════════════════════════════════════════════════════
TRAÇABILITÉ DES SOURCES AVEC PAGE (OBLIGATOIRE)
═══════════════════════════════════════════════════════════════════

Pour CHAQUE champ important, tu DOIS indiquer d'où vient l'information :

**Format PRÉFÉRÉ :** "Page X - [Citation exacte 10-20 mots]"

**Champs à tracer :**
1. Date signature → Cite le pattern exact trouvé
2. Scope → Indique où tu as trouvé (tableau, section)
3. Price Ramp-up → Cite le mot-clé ou la différence de prix
4. **Ramp up price → CRITIQUE : réponds aux deux questions A et B avec citations**
5. Setup fees → Liste les lignes exactes avec montants
6. TCV calculation → Détaille les tableaux et calculs
7. Durée → Cite la mention exacte

**Format source Ramp up price :**
"Q.A (Commercial?) → [OUI/NON] : [citation justificative]. Q.B (Périmètre?) → [OUI/NON] : [citation justificative]. Conclusion : [valeur]"

**Exemples :**

"Ramp up price - Commercial seul":
"Q.A → OUI : 'Le montant des trois premiers loyers sera de 50% du montant total'. Q.B → NON : scope identique sur toute la durée. → Commercial"

"Ramp up price - Périmètre seul":
"Q.A → NON : remise 20% présente dans Année 1, Année 2 ET Run (uniforme). Q.B → OUI : Collaborative 6→9 users, Viewer 4→6 entre Année 1 et Année 2. → Périmètre"

"Ramp up price - Mixte":
"Q.A → OUI : 'geste commercial -40% mois 1-2'. Q.B → OUI : FM Demand Phase 1 (5 users) → FM Demand+Supply Phase 2 (10 users). → Périmètre + Commercial"

**Si "Not found" :**
"Date signature": "Not found - Aucune date DocuSign ou signature visible dans le contrat"

═══════════════════════════════════════════════════════════════════
FORMAT DE RÉPONSE
═══════════════════════════════════════════════════════════════════

RÉPONDS UNIQUEMENT avec ce JSON (SANS ```json, SANS texte avant/après):

{{
    "reasoning": "Description du raisonnement complet. Pour le ramp-up : réponse explicite à Q.A et Q.B avec les éléments du contrat qui les justifient.",
    "sources": {{
        "Date signature": "Page 1 - DocuSigned by: Date: 19-nov.-2025 | 09:41:57 CET",
        "Scope": "Page 3 - Tableau Service Financial Conditions - FM Demand Planning",
        "Price Ramp-up": "Page 3-4 - Tableaux Année 1 et Année 2 avec montants différents",
        "Ramp up price": "Q.A → OUI : 'geste commercial -40% mois 1-2'. Q.B → OUI : Demand Phase 1 (5 users) → Demand+Supply Phase 2 (10 users). → Périmètre + Commercial",
        "Setup fees": "Page 5 - Formation: 3,000€ + Onboarding: 3,000€",
        "TCV": "Page 3-4 - MRR standard 6,000€ × 36 = 216,000€. Year 1 réduit → Écart 24,000€",
        "Durée": "Page 2 - Section Term: 'period of three (3) years'"
    }},
    "Client Name": "{client_name}",
    "Type de contrat": "SaaS",
    "Contrat format Sunstice": "Yes",
    "Date signature": "19/11/2025",
    "Scope": "Demand",
    "Durée du Contrat": "3 ans",
    "Price Ramp-up": "Yes",
    "Ramp up price": "Périmètre + Commercial",
    "Ramp up price impact € vs TCV": 24000,
    "Ramp-up price % TCV": 11.11,
    "IFRS 15 AGI": "No",
    "Option Sortie avant terme du contrat": "Résiliation anticipée moyennant préavis de 3 mois",
    "SaaS Start Date": "19/11/2025",
    "Start date ignition": "Start after Design",
    "End date théorique": "18/11/2028",
    "Setup fees": "Yes",
    "Setup fees €": 6000
}}
"""
    
    def analyze_with_bedrock(self, contract_text: str, agi_threshold: float, client_name: str) -> Tuple[Dict, Dict]:     
        prompt = self._get_base_prompt(contract_text, agi_threshold, client_name)

        try:
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 5000,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }
            
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body)
            )
            
            response_body = json.loads(response['body'].read())
            assistant_message = response_body['content'][0]['text']
            
            # Extraire le JSON
            import re
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', assistant_message, re.DOTALL)
            
            if json_match:
                result = json.loads(json_match.group())
            else:
                raise Exception(f"Pas de JSON trouvé dans la réponse: {assistant_message[:200]}")
            
            # Preuves
            evidence = {
                "mode": "bedrock",
                "model": self.model_id,
                "text_length": len(contract_text),
                "response_full": assistant_message,
                "timestamp": datetime.now().isoformat()
            }
            
            return result, evidence
            
        except Exception as e:
            raise Exception(f"Erreur Bedrock: {str(e)}")
    
    def analyze_multi_documents(
        self, 
        texts_dict: Dict[str, str], 
        agi_threshold: float, 
        client_name: str
    ) -> Tuple[Dict, Dict]:
        """Analyse multi-documents AVEC fusion date intelligente"""
        
        context = self._build_multi_doc_context(texts_dict)
        prompt = self._get_base_prompt(context, agi_threshold, client_name)
        
        try:
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 5000,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }
            
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body)
            )
            
            response_body = json.loads(response['body'].read())
            assistant_message = response_body['content'][0]['text']
            
            import re
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', assistant_message, re.DOTALL)
            
            if json_match:
                result = json.loads(json_match.group())
            else:
                raise Exception(f"Pas de JSON trouvé dans la réponse: {assistant_message[:200]}")
            
            if len(texts_dict) > 1:
                date_sig = result.get("Date signature", "")
                vague_patterns = ["not found", "non visible", "non spécifié", "effective date", "n/a"]
                is_vague = any(p in date_sig.lower() for p in vague_patterns) if date_sig else True
                
                if is_vague:
                    master_date = self._extract_date_from_master_agreement(texts_dict)
                    if master_date:
                        result["Date signature"] = master_date
                        
                        if "sources" not in result:
                            result["sources"] = {}
                        
                        old_source = result["sources"].get("Date signature", "")
                        result["sources"]["Date signature"] = f"Master Agreement - Dated {master_date} (remplace: {old_source})"
                        
                        if "reasoning" in result:
                            result["reasoning"] += f"\n\n POST-PROCESSING: Date signature extraite du Master Agreement ({master_date}) car date SaaS Agreement était vague/manquante."
            
            evidence = {
                "mode": "bedrock_multi_docs",
                "model": self.model_id,
                "documents_analyzed": list(texts_dict.keys()),
                "total_text_length": sum(len(t) for t in texts_dict.values()),
                "response_full": assistant_message,
                "timestamp": datetime.now().isoformat()
            }
            
            return result, evidence
            
        except Exception as e:
            raise Exception(f"Erreur Bedrock multi-docs: {str(e)}")