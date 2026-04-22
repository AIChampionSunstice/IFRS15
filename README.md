# Système IFRS15 - Analyse Automatique de Contrats SaaS
**Date:** Avril 2026  
**Auteur:** Équipe Finance Sunstice  

---

## 🎯 **OBJECTIF DU SYSTÈME**

Automatiser l'analyse des contrats SaaS pour la conformité IFRS15 en utilisant :
- **AWS Textract** : Extraction OCR du texte et tableaux
- **AWS Bedrock (Claude Sonnet 4.5)** : Analyse intelligente IA
- **Streamlit** : Interface web sécurisée

---

## 📁 **STRUCTURE DU PROJET**
Projet IFRS15/
├── .streamlit/
│   ├── config.toml          # Configuration UI Streamlit
│   └── secrets.toml         # SECRETS AWS (NE PAS COMMITER)
│
├── core/                    # Logique métier
│   ├── auth.py              # Authentification utilisateurs
│   ├── aws_services.py      # Intégration AWS (Bedrock, Textract, S3)
│   ├── classify_docs.py     # Classification automatique documents
│   ├── file_io.py           # Gestion fichiers (upload, ZIP)
│   ├── pdf_annotate.py      # Annotations PDF avec sources
│   ├── real_analyzer.py     # Analyse contrats + post-processing
│   ├── session_manager.py   # Gestion sessions + déduplication
│   └── visualisations.py    # Graphiques et metrics
│
├── data/                    # Données persistantes
│   ├── contracts/           # Contrats analysés (JSON)
│   │   └── contracts.json
│   └── .session             # Session utilisateur (pickle)
│
├── pages/                   # Pages Streamlit
│   ├── 1_Upload.py          # Upload fichiers (PDF/ZIP)
│   ├── 2_Chatbot.py         # Assistant IA conversationnel
│   ├── 3_Dashboard.py       # Vue d'ensemble contrats
│   └── 5_Preuves.py         # Preuves extraction + sources
│
├── app.py                   # Point d'entrée application
└── README.md                # Ce fichier

---

## **INSTALLATION ET LANCEMENT**

### **1. Prérequis**
Pour pouvoir faire tourner ce système sur vos ordinateurs il est impératif de télécharger certains prérequis :
```bash
Python 3.9+
pip install streamlit boto3 PyMuPDF pandas plotly
```
### **2. Configuration AWS**
La configuration est la partie l'une des partie les plus importante ! Je rappelle que cette partie ne doit pas être communiqué hors Sunstice, donc avec aucune IA ⚠️
Créer `.streamlit/secrets.toml` :
```[aws]
bucket_name = "ifrs15-contracts-sunstice-us"
access_key_id = "AKIAXXXXXXXXXXXXXXXX"
secret_access_key = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
region = "us-east-1"
```
**⚠️ IMPORTANT : Ce fichier DOIT être dans `.gitignore` !**

### **3. Lancer l'application**
Rien de plus simple, il suffit d'aller dans le terminal de votre IDE, pour ma part c'était VSCode et ensuite ouvrir le fichier a l'emplacement prévu et lancer cette commande :
```bash
streamlit run app.py
```
**Interface accessible sur : http://localhost:8501**

---

## **SÉCURITÉ**
### **Authentification**
- Email : `finance@sunstice.com`
- Mot de passe : `Finance`

### **Session**
- Timeout automatique : 20 minutes d'inactivité
- Session persistante : `data/.session` (pickle)

### **FICHIERS À NE JAMAIS COMMITER**
```gitignore
.streamlit/secrets.toml
data/contracts/
data/.session
__pycache__/
```
---

## **FLUX D'UTILISATION**
### **Étape 1 : Upload**
`pages/1_Upload.py`
- Upload PDF ou ZIP multi-clients
- Extraction automatique si ZIP
- Classification documents (Master, SaaS, Order Form, Addendum)

### **Étape 2 : Analyse**
`core/real_analyzer.py` + `core/aws_services.py`
1. Upload S3
2. Textract OCR (texte + tableaux)
3. Prompt Claude 750+ lignes
4. Post-processing IFRS15
5. Validation anti-hallucination

### **Étape 3 : Preuves**
`pages/5_Preuves.py`
- Affichage sources extraites
- Calcul confiance dynamique (0-95%)
- Annotations PDF colorées

### **Étape 4 : Dashboard**
`pages/3_Dashboard.py`
- Vue d'ensemble tous contrats
- Graphiques TCV, conformité IFRS
- Export Excel

---

## **FICHIERS CLÉS**
### **aws_services.py (750+ lignes)**
**Rôle :** Interface avec AWS Bedrock  
**Prompt IA :** 
- Exemples fictifs (pas de contamination)
- Règles anti-hallucination strictes
- Calcul TCV en 4 étapes
- Traçabilité sources avec pages

**Fonctions principales :**
```python
upload_to_s3(file_path, s3_key)           # Upload S3
extract_text_with_textract(s3_key)        # OCR Textract
classify_document_type(text)              # Classification auto
analyze_with_bedrock(contract_text, ...)  # Analyse single-doc
analyze_multi_documents(texts_dict, ...)  # Analyse multi-docs
```

---

### **real_analyzer.py**
**Rôle :** Orchestration analyse + post-processing

**Fonctions principales :**
```python
analyze_contract_real(...)                # Point d'entrée
apply_ifrs_rules(result, agi_threshold)   # Calcul IFRS 15 AGI
fix_setup_fees(result)                    # Normalisation setup fees
format_duration_human(result)             # Format durée ("36 mois")
validate_result_quality(result)           # Anti-hallucination
```

**Post-processing pipeline :**
Bedrock → apply_ifrs_rules → fix_setup_fees → format_duration_human → validate_result_quality

---

### **session_manager.py**
**Rôle :** Gestion contrats + déduplication

**Déduplication automatique :**
```python
def add_contract(contract_data):
    client_name = contract_data.get('Client Name')
    
    # Cherche doublon
    for idx, existing in enumerate(st.session_state.contracts):
        if existing.get('Client Name') == client_name:
            # REMPLACER l'ancien
            st.session_state.contracts[idx] = contract_data
            return
    
    # AJOUTER nouveau
    st.session_state.contracts.append(contract_data)
```

---

### **pdf_annotate.py**
**Rôle :** Annotations visuelles PDF

**Fonctionnalités :**
- Rectangles colorés par type de champ
- Extraction termes depuis sources (guillemets, dates, montants)
- Légende sur première page

**Exemple :**
```python
annotate_pdf_with_sources(
    pdf_path="/path/input.pdf",
    sources_dict={
        "Date signature": "Page 1 - DocuSigned by: 19-nov.-2025",
        "Setup fees": "Page 5 - Formation: 6,000€"
    },
    output_path="/path/output_annotated.pdf"
)
```

---

## **PAGES STREAMLIT**

### **app.py (Page d'accueil)**
- Login/Logout
- Indicateur session restante
- Navigation

### **1_Upload.py**
- Upload PDF/ZIP
- Sélection AGI threshold
- Lancement analyse
- Téléchargement PDF annoté

### **2_Chatbot.py**
- Assistant IA conversationnel
- Questions sur contrats
- Historique chat

### **3_Dashboard.py**
- Tableau tous contrats
- Graphiques (TCV, conformité, scope)
- Export Excel

### **5_Preuves.py**
- Affichage sources JSON
- Calcul confiance dynamique
- Couleurs : Vert (trouvé), Jaune (partiel), Rouge (manquant)

---

## **CONFIGURATION**

### **config.toml**
```toml
[theme]
primaryColor = "#3b82f6"        # Bleu Sunstice
backgroundColor = "#ffffff"
textColor = "#1e293b"

[server]
port = 8501
enableXsrfProtection = true     # Protection CSRF

[runner]
fastReruns = true               # Performance
```

---

## **CHAMPS EXTRAITS (17)**

| # | Champ | Type | Exemple |
|---|-------|------|---------|
| 1 | Client Name | Texte | "Acme Corp" |
| 2 | Type de contrat | Texte | "SaaS" |
| 3 | Contrat format Sunstice | Yes/No | "Yes" |
| 4 | Date signature | DD/MM/YYYY | "19/11/2025" |
| 5 | Scope | Texte | "Demand, Supply" |
| 6 | Durée du Contrat | Texte | "36 mois" |
| 7 | Price Ramp-up | Yes/No | "Yes" |
| 8 | Ramp up price | Texte | "Commercial" |
| 9 | Ramp up price impact € vs TCV | Nombre | 12000 |
| 10 | Ramp-up price % TCV | Nombre | 3.92 |
| 11 | IFRS 15 AGI | Yes/No | "Yes" |
| 12 | Option Sortie | Texte | "Préavis 3 mois" |
| 13 | SaaS Start Date | DD/MM/YYYY | "19/11/2025" |
| 14 | Start date ignition | Texte | "Start after Design" |
| 15 | End date théorique | DD/MM/YYYY | "18/11/2028" |
| 16 | Setup fees | Yes/No | "Yes" |
| 17 | Setup fees € | Nombre | 6000 |

---

## **ERREURS FRÉQUENTES**

### **Erreur : "Bedrock timeout"**
**Cause :** Document trop long (> 50,000 caractères)  
**Solution :** Utiliser troncature dans aws_services.py

### **Erreur : "Date signature = Not found"**
**Cause :** Pattern DocuSign non détecté  
**Solution :** Vérifier prompt règles détection dates

### **Erreur : "Contrats en double"**
**Cause :** Analyse même client plusieurs fois  
**Solution :** Déduplication automatique session_manager.py

---

## **SUPPORT**

**Contact :** antoine.guerin@sunstice.com 
**Directeur Sécurité :** 
**Reprise code :** Voir ARCHITECTURE.md (documentation technique complète)

---

## **CHANGELOG**

**Version  (Avril 2026)**
- Prompt 750+ lignes sans contamination
- Anti-hallucination ("Not found" si < 95% confiance)
- Multi-docs avec fusion date Master Agreement
- Annotations PDF avec PyMuPDF
- Déduplication contrats automatique

**Version (Mars 2026)**
- Calcul TCV corrigé (4 étapes)
- Confiance dynamique 0-95%

**Version (Février 2026)**
- Première version fonctionnelle

---

## **AVANT MISE EN PRODUCTION**

### **CHECKLIST SÉCURITÉ**
- [ ] Changer MD5 → SHA256 dans auth.py
- [ ] Vérifier `.gitignore` contient secrets.toml
- [ ] Supprimer fichiers tests (test_*.py, mock_analyzer.py)
- [ ] Configurer secrets sur Streamlit Cloud (pas dans code)
- [ ] Tester timeout session (20 min)
- [ ] Valider permissions S3 (lecture/écriture bucket uniquement)

---
