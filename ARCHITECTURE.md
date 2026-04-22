# ARCHITECTURE TECHNIQUE — Système IFRS15
**Date :** Avril 2026  
**Auteur :** Équipe Finance Sunstice

---

## 1. VUE D'ENSEMBLE
Le système IFRS15 est une application web Streamlit qui automatise l'analyse de conformité IFRS15 sur les contrats SaaS FuturMaster. Il orchestre trois services AWS (S3, Textract, Bedrock) et expose une interface multi-pages sécurisée.
```
Utilisateur (navigateur)
        │
        ▼
  app.py (login)
        │
        ├── pages/1_Upload.py      → Upload & déclenchement analyse
        ├── pages/2_Chatbot.py     → Assistant conversationnel
        ├── pages/3_Dashboard.py   → Vue d'ensemble / export
        └── pages/5_Preuves.py     → Sources & preuves visuelles
                │
                ▼
           core/ (logique métier)
                │
     ┌──────────┼──────────────────────┐
     ▼          ▼                      ▼
 auth.py   real_analyzer.py      session_manager.py
             │
     ┌───────┴────────┐
     ▼                ▼
aws_services.py   pdf_annotate.py
     │
  ┌──┴──────────────────┐
  ▼          ▼          ▼
AWS S3   Textract   Bedrock (Claude)
```

---

## 2. ARBORESCENCE COMPLÈTE

```
Projet IFRS15/
├── .streamlit/
│   ├── config.toml              # Thème UI, serveur, CSRF
│   └── secrets.toml             # AWS credentials (NE PAS COMMITER)
│
├── core/                        # Logique métier (pas de Streamlit UI ici)
│   ├── auth.py                  # Authentification + session disque
│   ├── aws_services.py          # Classe AWSServices : S3 / Textract / Bedrock
│   ├── classify_docs.py         # Classification par nom de fichier
│   ├── client_matcher.py        # Matching client Excel / fuzzy
│   ├── file_io.py               # Upload fichiers, extraction ZIP sécurisée
│   ├── mock_analyzer.py         # (obsolète, à supprimer)
│   ├── pdf_annotate.py          # Annotation PDF avec PyMuPDF
│   ├── real_analyzer.py         # Orchestration analyse + post-processing
│   ├── session_manager.py       # Persistance contrats + déduplication
│   └── visualisations.py        # Graphiques Plotly
│
├── data/                        # Données runtime (NE PAS COMMITER)
│   ├── contracts/
│   │   └── contracts.json       # Contrats analysés (JSON)
│   └── .session                 # Session pickle (binaire)
│
├── pages/
│   ├── 1_Upload.py              # Page upload + analyse
│   ├── 2_Chatbot.py             # Assistant IA
│   ├── 3_Dashboard.py           # Tableau de bord
│   └── 5_Preuves.py             # Preuves et sources
│
├── app.py                       # Point d'entrée (login + navigation)
├── list_all_models.py           # Script test (à déplacer dans tests/)
├── list_inference_profiles.py   # Script test (à déplacer dans tests/)
├── test_aws_simple.py           # Script test (à déplacer dans tests/)
└── test_aws.py                  # Script test (à déplacer dans tests/)
```

---

## 3. DESCRIPTION DÉTAILLÉE DE CHAQUE FICHIER

### 3.1 `app.py` — Point d'entrée

**Rôle :** Page d'accueil, gestion login/logout, affichage métriques globales.

**Ce qu'il fait :**
- Initialise la config Streamlit (`set_page_config`)
- Gère l'authentification : affiche le formulaire si non connecté, vérifie timeout 20 min
- Après connexion : initialise `SessionManager`, affiche les 4 métriques (contrats, conformes, TCV, taux)
- Sidebar : configuration AGI threshold, seuil déduplication, bouton reset DB, info session

**Ce qu'il NE doit PAS faire :**
- Contenir de logique métier IFRS15
- Appeler directement AWS
- Dupliquer la logique d'auth (qui est dans `core/auth.py`)

> ⚠️ **Attention :** `app.py` duplique actuellement certaines fonctions de `core/auth.py` (hash_password, USERS, SESSION_FILE). La version canonique est `core/auth.py`. Si tu modifies les utilisateurs ou le mot de passe, tu dois le faire dans **les deux fichiers**.

---

### 3.2 `core/auth.py` — Authentification

**Rôle :** Gestion complète de l'authentification et des sessions.

**Fonctions clés :**

| Fonction | Description |
|----------|-------------|
| `_hash(password)` | Hash MD5 du mot de passe (voir SECURITY.md) |
| `check_credentials(email, password)` | Vérifie email + mot de passe hashé |
| `login(email)` | Initialise la session Streamlit + sauvegarde disque |
| `logout()` | Efface la session mémoire et disque |
| `require_auth()` | À appeler en début de chaque page protégée |
| `check_timeout()` | Retourne True si inactivité > 20 min |
| `update_activity()` | Met à jour `last_activity`, sauvegarde disque toutes les 2 min |
| `save_session()` / `load_session()` | Persistance pickle sur `data/.session` |

**Flux login :**
```
require_auth() appelé
    │
    ├─ is_logged_in() = True → check_timeout() → update_activity() → OK
    │
    └─ is_logged_in() = False → load_session() depuis disque
            │
            ├─ Session valide → update_activity() → OK
            └─ Pas de session → st.stop() + message "retourner à l'accueil"
```

**USERS hardcodé :**
```python
USERS = {
    "finance@sunstice.com": {
        "password": _hash("Finance"),  # MD5 — voir SECURITY.md
        "name": "Finance",
        "role": "Equipe Finance"
    }
}
```

---

### 3.3 `core/aws_services.py` — Interface AWS

**Rôle :** Classe `AWSServices` qui encapsule toutes les interactions avec AWS.

**Initialisation :**
Les credentials sont lus exclusivement depuis `st.secrets['aws']` (jamais hardcodés).

**Méthodes principales :**

| Méthode | Entrée | Sortie | Description |
|---------|--------|--------|-------------|
| `upload_to_s3(file_path, s3_key)` | Path local, clé S3 | URL S3 | Upload binaire vers S3 |
| `extract_text_with_textract(s3_key)` | Clé S3 | Texte brut | OCR asynchrone (polling toutes 5s, max 5 min) |
| `classify_document_type(text)` | Texte brut | String type | Regex sur keywords (Master, SaaS, Order Form…) |
| `analyze_with_bedrock(text, threshold, client)` | Texte, seuil %, nom client | (dict résultat, dict preuves) | Analyse single-document |
| `analyze_multi_documents(texts_dict, threshold, client)` | Dict {type: texte}, seuil, nom | (dict résultat, dict preuves) | Analyse multi-documents avec fusion date |

**Modèle utilisé :**  
`global.anthropic.claude-sonnet-4-5-20250929-v1:0` via AWS Bedrock  
`temperature: 0`, `max_tokens: 5000`

**Le prompt (méthode `_get_base_prompt`) fait ~750 lignes et contient :**
- Règles anti-hallucination (seuil 95% de confiance)
- Méthode calcul TCV en 4 étapes avec exemples fictifs
- Détection ramp-up en 6 méthodes
- Règles de classification Commercial / Périmètre / Mixte
- Format JSON de sortie strict (17 champs)
- Traçabilité sources obligatoire

**Gestion multi-docs :**
```
texts_dict = {
    "Master Agreement (MSA.pdf)": "texte extrait...",
    "SaaS Agreement (Contract.pdf)": "texte extrait...",
    "Order Form (Order.pdf)": "texte extrait..."
}
```
`_build_multi_doc_context()` assemble tous les textes en un seul prompt avec séparateurs visuels.  
Post-analyse : si la date signature est vague dans la réponse Bedrock, `_extract_date_from_master_agreement()` la récupère directement depuis le Master Agreement via regex.

---

### 3.4 `core/real_analyzer.py` — Orchestration

**Rôle :** Coordonne tout le pipeline d'analyse et applique les règles post-IA.

**Fonction principale :** `analyze_contract_real(contract_dir, agi_threshold, contract_label)`

**Pipeline complet :**
```
1. Lister les PDF dans contract_dir
2. Upload chaque PDF vers S3 (s3://bucket/contracts/{label}/{fichier.pdf})
3. Textract OCR sur chaque PDF → texte brut + tableaux
4. classify_document_type() sur chaque texte → dict {type: texte}
5. Si > 1 fichier → analyze_multi_documents() sinon analyze_with_bedrock()
6. Post-processing (dans l'ordre) :
   a. sanitize_rampup_value()   → normalise "Périmètre+Commercial" etc.
   b. apply_ifrs_rules()        → calcule IFRS 15 AGI selon seuil
   c. fix_setup_fees()          → cohérence Setup fees Yes/No vs €
   d. format_duration_human()   → "36 mois" → "3 ans"
   e. validate_result_quality() → dates invalides → "Not found", négatifs → 0
```

**Règles post-processing détaillées :**

`apply_ifrs_rules()` :
- Si `Ramp up price` = "Périmètre" (pur) → `% TCV = 0`, `IFRS 15 AGI = "Yes"`
- Sinon → compare `Ramp-up price % TCV` au seuil AGI

`fix_setup_fees()` :
- Cherche montants € dans le champ `sources["Setup fees"]`
- Si montant trouvé → `Setup fees = "Yes"`, `Setup fees € = montant`
- Si pas de montant → `Setup fees = "No"`, `Setup fees € = 0`

---

### 3.5 `core/session_manager.py` — Persistance

**Rôle :** Gestion du cycle de vie des contrats analysés.

**Stockage :** `data/contracts/contracts.json`

**Déduplication automatique :**
Avant d'ajouter un contrat, `_find_similar_contract()` compare le nom client avec tous les existants via `SequenceMatcher`. Seuil configurable (défaut 85%).

```
add_contract("Nutrition et Santé")
    │
    └─ Similarity("Nutrition et Santé", "NUTRITION ET SANTE FRANCE") = 0.87 > 0.85
           → REMPLACE l'existant (warning affiché)
```

**Config persistante dans `st.session_state.config` :**
- `agi_threshold` : seuil AGI (défaut 10%)
- `similarity_threshold` : seuil déduplication (défaut 0.85)
- `auto_classify` : classification auto
- `show_evidence` : affichage preuves
- `export_format` : format export ('excel')

---

### 3.6 `core/client_matcher.py` — Identification clients

**Rôle :** Identifier le client d'un PDF/ZIP en le comparant à une liste Excel.

**Source de vérité :** `clients.xlsx` (cherché dans CWD, project root, `data/`)

**Algorithme de matching (score de 0 à 1) :**
1. Égalité exacte → 1.0
2. Inclusion (A dans B ou B dans A) → 0.9
3. Jaccard sur tokens (≥3 chars) → 0 à 0.7
4. Bonus si tous les tokens du client sont dans le candidat

**Seuils :**
- Fichier PDF individuel : 0.45
- Nom de ZIP : 0.60

**Priorités dans `group_pdfs_by_client_smart()` :**
```
0. Nom du ZIP → si score ≥ 0.60 → TOUS les PDFs = ce client
1. Token commun dans noms de fichiers → batch mono-client
2. Pattern "FuturMaster / CLIENT" dans le contenu
3. Matching nom de fichier vs liste
4. Matching texte vs liste
5. Fallback : nom de fichier nettoyé
```

---

### 3.7 `core/pdf_annotate.py` — Annotations PDF

**Rôle :** Annoter visuellement le PDF de sortie pour localiser les extractions IA.

**Librairie :** PyMuPDF (`fitz`)

**Couleurs par champ :**
- Rouge : Date signature
- Vert : Scope
- Orange : Price Ramp-up, Ramp up price
- Bleu : Setup fees
- Magenta : TCV
- Violet : Durée du Contrat
- Cyan : SaaS Start Date

**Processus d'annotation :**
1. `extract_search_terms(source_text, field_name)` → extrait termes recherchables depuis les sources JSON
2. `fuzzy_search_in_page()` → cherche chaque terme, filtre faux positifs (numéros de page, headers/footers)
3. Pour chaque occurrence : highlight coloré + icône Note
4. `capture_screenshot_around_rect()` → screenshot PNG de la zone (preuve visuelle)
5. `add_legend()` → légende colorée en haut de page 1

**Anti-faux positifs :**
- Filtre `is_page_number()` : exclut les chiffres isolés qui matcheraient des montants
- Filtre `is_in_footer_or_header()` : ignore les 50px haut/bas de page (sauf pour dates signature)

---

### 3.8 `core/classify_docs.py` — Classification

**Rôle :** Classer un document selon son nom de fichier.

**Priorités (ordre d'évaluation) :**
1. ORDER_FORM si "order form" ou "subscription services order form"
2. SOW si "sow" ou "statement of work"
3. SLA si "sla"
4. SUPPORT si "support"
5. MASTER si "subscription agreement", "saas subscription", "msa", "master"
6. OTHER sinon

---

### 3.9 `core/file_io.py` — Gestion fichiers

**Rôle :** Upload Streamlit → disque, extraction ZIP sécurisée.

**Protection zip-slip :**
```python
member_path = (dest_dir / member).resolve()
if not str(member_path).startswith(str(dest_dir.resolve())):
    raise ValueError("ZIP invalide (zip-slip).")
```
Empêche un ZIP malveillant d'écrire des fichiers hors du dossier cible.

---

### 3.10 `core/visualisations.py` — Graphiques

**Rôle :** Classe `IFRS15Visualizer` avec méthodes statiques pour les graphiques Plotly.

| Méthode | Graphique |
|---------|-----------|
| `create_agi_gauge(pct, threshold)` | Jauge % AGI vs TCV |
| `create_contract_timeline(contracts)` | Timeline scatter des contrats |
| `create_revenue_distribution(contracts)` | Bar chart montants ramp-up |
| `create_ifrs15_compliance_pie(contracts)` | Camembert conformité |
| `create_summary_metrics(contracts)` | Dict des 4 métriques globales |

---

## 4. PAGES STREAMLIT

### `pages/1_Upload.py`

**Ce que fait cette page :**
- Upload d'un ou plusieurs PDF, ou d'un ZIP
- Si ZIP : extraction + identification clients via `client_matcher`
- Sélection du seuil AGI
- Bouton "Analyser" → appelle `analyze_contract_real()`
- Affichage résultats JSON
- Téléchargement PDF annoté

**Ce qu'il NE faut PAS mettre ici :**
- Logique de calcul IFRS15 (elle est dans `real_analyzer.py`)
- Connexion AWS directe (passe par `AWSServices`)

---

### `pages/2_Chatbot.py`

**Ce que fait cette page :**
- Interface conversationnelle avec Bedrock
- Questions libres sur les contrats analysés
- Historique de conversation en session

---

### `pages/3_Dashboard.py`

**Ce que fait cette page :**
- Tableau de tous les contrats (`SessionManager.get_contracts()`)
- Graphiques : camembert conformité, bar chart TCV, timeline
- Export Excel via `pandas`

**Ce qu'il NE faut PAS mettre ici :**
- Boutons de relance d'analyse (réservé à Upload)

---

### `pages/5_Preuves.py`

**Ce que fait cette page :**
- Affiche le dict `sources` du dernier contrat analysé
- Calcul visuel de confiance par champ (vert/jaune/rouge)
- Affichage screenshots PNG des annotations

**Logique de confiance (exemple) :**
- `"Not found"` → Rouge (0%)
- Source avec citation ("Page 3 - ...") → Vert (80-95%)
- Source courte sans page → Jaune (50%)

---

## 5. FLUX DE DONNÉES COMPLET

### Upload d'un ZIP multi-clients

```
ZIP uploadé
    │
    ├─ file_io.extract_zip_to_dir()
    │
    ├─ client_matcher.group_pdfs_by_client_smart()
    │       └─ Groupe PDFs par client → dict {client: [pdf1, pdf2...]}
    │
    └─ Pour chaque client :
            │
            ├─ real_analyzer.analyze_contract_real(dir_client, threshold, label)
            │       │
            │       ├─ aws_services.upload_to_s3() × N PDFs
            │       ├─ aws_services.extract_text_with_textract() × N PDFs
            │       ├─ aws_services.classify_document_type() × N PDFs
            │       ├─ aws_services.analyze_multi_documents() → résultat brut
            │       └─ Post-processing (5 fonctions)
            │
            ├─ session_manager.add_contract(result)
            │
            └─ pdf_annotate.annotate_pdf_with_sources()
```

---

## 6. CONFIGURATION

### `.streamlit/config.toml`

```toml
[theme]
primaryColor = "#3b82f6"           # Bleu Sunstice
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f8fafc"
textColor = "#1e293b"

[server]
port = 8501
enableXsrfProtection = true        # Protection CSRF activée
enableCORS = false                  # CORS désactivé

[browser]
gatherUsageStats = false            # Pas de télémétrie
```

### `.streamlit/secrets.toml` (NE PAS COMMITER)

```toml
[aws]
bucket_name = "..."
access_key_id = "..."
secret_access_key = "..."
region = "..."
```

---

## 7. DÉPENDANCES

| Package | Usage |
|---------|-------|
| `streamlit` | Framework UI web |
| `boto3` | SDK AWS (S3, Textract, Bedrock) |
| `PyMuPDF` (`fitz`) | Lecture/annotation PDF |
| `pandas` | Manipulation données, export Excel |
| `plotly` | Graphiques interactifs |
| `Pillow` | Traitement images screenshots |
| `openpyxl` | Export .xlsx |

---

## 8. REPRISE DU CODE — CHECKLIST

Si tu reprends ce projet, voici l'ordre de lecture recommandé :

1. Lire `SECURITY.md` en premier (credentials, mots de passe)
2. Configurer `.streamlit/secrets.toml` avec les vraies credentials AWS
3. Lancer `streamlit run app.py` et tester le login
4. Uploader un PDF de test simple (pas de ZIP) via la page 1
5. Vérifier que S3 reçoit bien le fichier dans le bucket
6. Vérifier que Textract extrait le texte
7. Vérifier que Bedrock retourne un JSON valide
8. Si tout fonctionne, tester un ZIP multi-clients

**Points fragiles à surveiller :**
- La duplication de `USERS` entre `app.py` et `core/auth.py` (si on change le mot de passe, changer dans les deux)
- Le modèle Bedrock `claude-sonnet-4-5-20250929-v1:0` — à mettre à jour si déprécié
- Le fichier `data/.session` (pickle) — peut poser des problèmes de permissions sur certains déploiements
- Sur Streamlit Cloud, `data/` est éphémère entre redémarrages — prévoir une solution de persistance externe si besoin

---