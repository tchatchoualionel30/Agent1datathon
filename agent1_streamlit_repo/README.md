# CrisisAI War Room — Agent 1 Streamlit

Application Streamlit pour transformer le notebook **Agent 1 — Analyste de crise** en dashboard déployable.

L'app permet d'importer un fichier `data.xlsx`, `.csv` ou n'importe quel corpus équivalent, puis de produire les mêmes résultats que le notebook :

- KPIs globaux du corpus ;
- timeline journalière et horaire ;
- détection automatique des pics ;
- narratifs dominants par mots-clés ;
- top auteurs, top hashtags, top posts ;
- Crisis Velocity Score ;
- brief Agent 1 ;
- exports CSV + rapport Markdown pour les slides et les prochains agents.

## Structure du repo

```text
.
├── app.py                         # Application Streamlit principale
├── requirements.txt               # Dépendances pour Streamlit Cloud
├── src/
│   ├── agent1_core.py             # Toute la logique du notebook transformée en fonctions/classes
│   └── llm_clients.py             # Option OpenRouter pour réécrire le brief
├── notebooks/
│   └── agent-1-datathon.ipynb     # Notebook d'origine conservé dans le repo
├── prompts/
│   └── agent1_openrouter_prompt.md
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example
└── data/
    └── .gitkeep                   # Dossier optionnel pour fichiers locaux non commités
```

## Lancer en local

```bash
python -m venv .venv
source .venv/bin/activate  # Mac/Linux
# .venv\Scripts\activate   # Windows
pip install -r requirements.txt
streamlit run app.py
```

Ensuite, importe ton fichier `data.xlsx` ou un CSV depuis la barre latérale.

## Déployer sur Streamlit Cloud

1. Créer un repo GitHub.
2. Mettre tous les fichiers de ce dossier dans le repo.
3. Aller sur Streamlit Cloud.
4. Choisir le repo.
5. Main file path : `app.py`.
6. Déployer.

## OpenRouter optionnel

L'app fonctionne sans LLM externe grâce au brief déterministe.

Pour activer la réécriture du brief avec OpenRouter :

- soit entrer la clé temporairement dans la barre latérale ;
- soit ajouter dans les secrets Streamlit Cloud :

```toml
OPENROUTER_API_KEY = "my_openrouter_api_key_here"
```

Ne mets jamais ta vraie clé API directement dans GitHub.

## Colonnes minimales

Le fichier doit contenir au minimum :

- une colonne de date ;
- une colonne auteur ;
- une colonne texte/message.

Les colonnes suivantes améliorent l'analyse si elles existent :

- sentiment ;
- likes ;
- comments/replies ;
- shares/retweets ;
- reach ;
- impressions ;
- engagement type ;
- hashtags ;
- mentions ;
- followers.

## Démo Jour 2 conseillée

1. Importer `data.xlsx`.
2. Montrer les KPIs globaux.
3. Montrer les pics détectés.
4. Analyser le pic principal ou la période du 26–27 mars.
5. Montrer le Crisis Velocity Score.
6. Montrer le brief, les narratifs, les comptes moteurs et les top posts.
7. Télécharger les exports pour alimenter Agent 2 et les slides Jour 3.

## Positionnement Top 1

Phrase à dire :

> Ce n'est pas un simple dashboard. C'est le premier module d'une War Room IA : l'Agent 1 observe et diagnostique, l'Agent 2 classera plus finement les narratifs, et l'Agent 3 proposera la stratégie de réponse.
