# Guide rapide GitHub + Streamlit Cloud

## 1. Mettre les fichiers sur GitHub

```bash
git init
git add .
git commit -m "Ajout Agent 1 Streamlit"
git branch -M main
git remote add origin https://github.com/TON_USER/TON_REPO.git
git push -u origin main
```

## 2. Déployer

- Va sur Streamlit Cloud.
- Clique sur **New app**.
- Sélectionne ton repo GitHub.
- `Main file path` : `app.py`.
- Clique sur **Deploy**.

## 3. Tester

Dans l'application :

- importe `data.xlsx` ;
- vérifie les KPIs ;
- va dans l'onglet **Agent 1 — Analyse période** ;
- analyse la période `2026-03-26 00:00:00` → `2026-03-27 23:59:00` ;
- télécharge les exports.

## 4. Pour les clés API

Ne jamais mettre une clé API dans le code.

Dans Streamlit Cloud :

```toml
OPENROUTER_API_KEY = "my_openrouter_api_key_here"
```
