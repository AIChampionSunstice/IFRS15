# SÉCURITÉ — Système IFRS15
**Date :** Avril 2026  
**Classification :** Interne / Confidentiel

---

## RÉSUMÉ EXÉCUTIF

Ce document liste tous les points de sécurité du système IFRS15 : ce qui est bien fait, ce qui doit être corrigé avant mise en production, et comment configurer le déploiement sans exposer de données sensibles.

---

## 1. AUDIT DES DONNÉES SENSIBLES DANS LE CODE

### Ce qui est CORRECT

**AWS Credentials — Aucun secret dans le code source**

Le fichier `core/aws_services.py` charge les credentials exclusivement via `st.secrets` :

```python
region = st.secrets['aws']['region']
self.bucket_name = st.secrets['aws']['bucket_name']
aws_access_key = st.secrets['aws']['access_key_id']
aws_secret_access_key = st.secrets['aws']['secret_access_key']
```

Résultat : si quelqu'un fait F12 dans le navigateur, inspecte le code source, ou accède au dépôt Git, **aucune clé AWS n'est visible**. Les credentials ne transitent jamais côté client.

**Aucune URL de bucket en dur**  
Aucune chaîne du type `"s3://ifrs15-..."` n'apparaît hardcodée dans le code.

**Aucun token API en dur**  
Aucun token Anthropic ou AWS dans le code source.

---

### PROBLÈME CRITIQUE #1 — Mots de passe hashés en MD5

**Localisation :** `core/auth.py` ligne 13 ET `app.py` ligne 10

```python
# CODE ACTUEL — DANGEREUX
def _hash(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()
```

**Pourquoi c'est dangereux :**  
MD5 n'est pas un algorithme de hachage de mots de passe. Il est conçu pour la vitesse, pas la sécurité. Le hash MD5 de `"Finance"` peut être cassé en moins d'une seconde sur des sites publics comme crackstation.net.

**Correction à apporter avant mise en production :**

```python
# REMPLACER par (dans auth.py ET app.py) :
import hashlib
import secrets as _secrets

def _hash(password: str, salt: str = None) -> tuple:
    if salt is None:
        salt = _secrets.token_hex(16)
    hashed = hashlib.sha256(f"{password}{salt}".encode()).hexdigest()
    return f"{salt}${hashed}"

def _verify(password: str, stored: str) -> bool:
    try:
        salt, _ = stored.split("$", 1)
        return _hash(password, salt) == stored
    except Exception:
        return False
```

Puis régénérer les hashes dans `USERS` en appelant `_hash("NouveauMotDePasse")`.

> **Note :** Pour une mise en production sérieuse, envisager `bcrypt` ou `argon2-cffi` qui sont des standards industriels pour le hachage de mots de passe.

---

### PROBLÈME #2 — Duplication de USERS entre deux fichiers

**Localisation :** `core/auth.py` ET `app.py`

Les deux fichiers définissent le dictionnaire `USERS` avec le même email et mot de passe. C'est un piège de maintenance : si on change le mot de passe dans l'un, on oublie l'autre.

**Correction :** `app.py` devrait importer depuis `core/auth.py` :

```python
# Dans app.py, remplacer la définition locale par :
from core.auth import USERS, check_credentials, login_user, logout_user
```

---

### PROBLÈME #3 — Fichier session en pickle

**Localisation :** `data/.session`

La session est sérialisée en format `pickle` Python. Ce format peut exécuter du code arbitraire s'il est modifié par un attaquant ayant accès au système de fichiers.

**Niveau de risque :** Faible en pratique (le fichier est local au serveur, pas accessible via HTTP), mais le risque existe si le serveur est compromis.

**Recommandation :** Sur Streamlit Cloud, ce fichier est isolé par déploiement et non accessible publiquement. Sur un déploiement custom, s'assurer que `data/` n'est pas exposé via un serveur web.

---

## 2. FICHIER secrets.toml — RÈGLES ABSOLUES

### Sur poste local (développement)

Le fichier `.streamlit/secrets.toml` contient les credentials AWS. Il ne doit **jamais** être commité sur Git.

**Vérifier le .gitignore :**

```gitignore
# Fichier à créer/compléter à la racine du projet
.streamlit/secrets.toml
data/contracts/
data/.session
__pycache__/
*.pyc
*.pyo
*.pyd
.env
venv/
env/
```

**Vérifier que le fichier n'est pas déjà dans Git :**

```bash
git status
# Si secrets.toml apparaît dans la liste → URGENCE

# Suppression de l'historique Git :
git rm --cached .streamlit/secrets.toml
echo ".streamlit/secrets.toml" >> .gitignore
git commit -m "Suppression secrets du dépôt"
```

Si les credentials ont déjà été exposés dans Git (même un seul commit), considérer les credentials comme compromis et en générer de nouveaux dans la console AWS.

---

### Sur Streamlit Cloud (production)

**Ne jamais uploader secrets.toml dans le dépôt.**  
Utiliser l'interface Streamlit Cloud :

```
Dashboard Streamlit Cloud
    → Sélectionner l'app
    → Settings
    → Secrets
    → Coller le contenu du secrets.toml
```

Format attendu :

```toml
[aws]
bucket_name = "ifrs15-contracts-sunstice-us"
access_key_id = "AKIAXXXXXXXXXXXXXXXX"
secret_access_key = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
region = "us-east-1"
```

---

## 3. CE QUI EST VISIBLE CÔTÉ CLIENT (F12)

Voici ce qu'un utilisateur peut voir en ouvrant les DevTools du navigateur sur l'application déployée :

| Élément | Visible ? | Commentaire |
|---------|-----------|-------------|
| Clés AWS | Non | Chargées côté serveur uniquement |
| Nom du bucket S3 | Non | Idem |
| Mot de passe hashé | Non | Jamais transmis au navigateur |
| Email des utilisateurs | Oui (dans app.py) | Lisible dans le code source Python si accès au dépôt — pas dans le navigateur |
| Nom du modèle Bedrock | Oui (dans aws_services.py) | Pas sensible |
| Structure du prompt | Oui (dans aws_services.py) | Pas sensible |

**Conclusion :** Aucune donnée confidentielle n'est exposée côté navigateur.

---

## 4. PERMISSIONS AWS RECOMMANDÉES

Le compte IAM utilisé (identifié par `access_key_id`) devrait avoir des permissions minimales :

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::ifrs15-contracts-sunstice-us/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "textract:StartDocumentAnalysis",
        "textract:GetDocumentAnalysis"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": "arn:aws:bedrock:*::foundation-model/anthropic.claude-*"
    }
  ]
}
```

**À vérifier :** Le compte IAM ne doit PAS avoir de droits administrateurs, ni d'accès à d'autres buckets S3.

---

## 5. CHECKLIST AVANT DÉPLOIEMENT STREAMLIT

À valider point par point avant de partager l'URL de l'application :

**Credentials AWS**
- [ ] `secrets.toml` absent du dépôt Git (`git status` ne le liste pas)
- [ ] `.gitignore` contient `.streamlit/secrets.toml`
- [ ] Secrets configurés dans l'interface Streamlit Cloud (pas dans le code)
- [ ] Permissions IAM AWS limitées au minimum nécessaire

**Authentification**
- [ ] MD5 remplacé par SHA256 (ou bcrypt) dans `core/auth.py` ET `app.py`
- [ ] Mot de passe "Finance" changé pour quelque chose de robuste (≥ 12 caractères)
- [ ] Timeout session à 20 minutes confirmé fonctionnel

**Fichiers à supprimer / déplacer**
- [ ] `test_aws.py` déplacé dans `tests/` ou supprimé
- [ ] `test_aws_simple.py` déplacé dans `tests/` ou supprimé
- [ ] `list_all_models.py` déplacé dans `tests/` ou supprimé
- [ ] `list_inference_profiles.py` déplacé dans `tests/` ou supprimé
- [ ] `core/mock_analyzer.py` supprimé (plus utilisé)

**Données**
- [ ] `data/contracts/` absent du dépôt Git (contient des données contractuelles)
- [ ] `data/.session` absent du dépôt Git

**Configuration**
- [ ] `enableXsrfProtection = true` dans `config.toml` (déjà fait)
- [ ] `enableCORS = false` dans `config.toml` (déjà fait)
- [ ] `gatherUsageStats = false` dans `config.toml` (déjà fait)

---

## 6. GESTION DES INCIDENTS

**Si des credentials AWS sont exposés accidentellement :**

1. Aller immédiatement dans la console AWS IAM
2. Désactiver la clé d'accès compromise
3. En générer une nouvelle
4. Mettre à jour `secrets.toml` et Streamlit Cloud
5. Vérifier les logs AWS CloudTrail pour détecter toute utilisation non autorisée
6. Prévenir le responsable sécurité

**Si le fichier .session est compromis :**

1. Supprimer `data/.session`
2. Tous les utilisateurs devront se reconnecter
3. Aucune donnée métier n'est dans ce fichier (seulement email + timestamp de connexion)

---

## 7. CE QUI N'EST PAS COUVERT PAR CE DOCUMENT

Ce document couvre la sécurité applicative du code Python/Streamlit. Les sujets suivants sont hors périmètre et relèvent de l'infrastructure :

- Sécurité du compte AWS (MFA, politique de rotation des clés)
- Chiffrement des données au repos dans S3 (SSE-S3 ou SSE-KMS)
- HTTPS / certificat TLS (géré par Streamlit Cloud)
- Logs d'accès et monitoring (CloudWatch, CloudTrail)
- Politique de rétention des données dans S3 (les PDF uploadés restent dans le bucket)

---
