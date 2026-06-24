# -*- coding: utf-8 -*-
"""Clients LLM optionnels pour améliorer le brief de l'Agent 1."""

from __future__ import annotations

import os
from typing import Optional

import requests

from .agent1_core import result_context_json


DEFAULT_MODEL = "openai/gpt-4o-mini"


def generate_openrouter_brief(result: dict, api_key: Optional[str] = None, model: str = DEFAULT_MODEL) -> str:
    """Génère un brief rédigé via OpenRouter, sans inventer de chiffres."""
    key = api_key or os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise ValueError("OPENROUTER_API_KEY manquant.")

    context = result_context_json(result)
    system = (
        "Tu es un analyste senior en communication de crise et réseaux sociaux. "
        "Tu restes neutre, factuel et prudent. Tu analyses une dynamique virale, pas une fake news. "
        "Tu n'inventes aucun chiffre : tu utilises uniquement le JSON fourni. "
        "Tu écris en français professionnel, utile pour une cellule de crise."
    )
    user = (
        "À partir du contexte JSON suivant, rédige un brief en 6 parties : "
        "1) diagnostic, 2) narratifs, 3) acteurs, 4) propagation, 5) risques, "
        "6) recommandations immédiates.\n\n"
        f"CONTEXTE_JSON:\n{context}"
    )

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://streamlit.io/",
            "X-Title": "CrisisAI War Room Agent 1",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "max_tokens": 1200,
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()
