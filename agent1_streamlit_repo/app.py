# -*- coding: utf-8 -*-
"""
CrisisAI War Room — Agent 1 Streamlit
Déploiement : streamlit run app.py
"""

from __future__ import annotations

import os
from datetime import datetime, time
from typing import Dict, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.agent1_core import (
    AnalysteDeCrise,
    auto_map_columns,
    build_daily_timeline,
    build_hourly_timeline,
    compute_kpis,
    crisis_level,
    detect_peaks_daily,
    detect_peaks_hourly,
    engagement_type_table,
    format_int,
    make_zip,
    narratives_table,
    preprocess_dataset,
    read_dataset,
    result_to_export_files,
    sentiment_table,
    top_authors,
    top_hashtags,
)
from src.llm_clients import DEFAULT_MODEL, generate_openrouter_brief


def get_streamlit_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


st.set_page_config(
    page_title="CrisisAI War Room — Agent 1",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded",
)


CUSTOM_CSS = """
<style>
.block-container {padding-top: 1.6rem; padding-bottom: 2rem;}
.metric-card {
    border: 1px solid rgba(128,128,128,0.20);
    border-radius: 18px;
    padding: 1rem 1.1rem;
    background: rgba(127,127,127,0.055);
    min-height: 104px;
}
.metric-title {font-size: 0.85rem; color: #777; margin-bottom: 0.25rem;}
.metric-value {font-size: 1.75rem; font-weight: 800; line-height: 1.2;}
.metric-note {font-size: 0.8rem; color: #777; margin-top: 0.3rem;}
.big-title {font-size: 2.1rem; font-weight: 900; margin-bottom: 0.1rem;}
.subtitle {color: #777; margin-bottom: 1rem;}
.warning-box {border-left: 5px solid #ffb000; padding: .8rem 1rem; background: rgba(255,176,0,.08); border-radius: 10px;}
.success-box {border-left: 5px solid #1aaf5d; padding: .8rem 1rem; background: rgba(26,175,93,.08); border-radius: 10px;}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Utils Streamlit
# -----------------------------------------------------------------------------

def show_metric_card(title: str, value: str, note: str = "") -> None:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-title">{title}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def cached_preprocess(file_bytes: bytes, file_name: str, mapping: Optional[Dict[str, Optional[str]]] = None):
    import io
    class UploadedLike:
        def __init__(self, data: bytes, name: str):
            self._data = data
            self.name = name
        def getvalue(self):
            return self._data

    raw = read_dataset(UploadedLike(file_bytes, file_name))
    df, used_mapping = preprocess_dataset(raw, mapping=mapping)
    return raw, df, used_mapping


def plot_timeline_daily(daily: pd.DataFrame):
    fig = px.line(daily, x="day", y="messages", markers=True, title="Timeline journalière — volume de messages")
    fig.update_layout(height=420, xaxis_title="Jour", yaxis_title="Messages")
    return fig


def plot_timeline_hourly(hourly: pd.DataFrame):
    fig = px.line(hourly, x="hour", y="messages", markers=True, title="Timeline horaire")
    fig.update_layout(height=420, xaxis_title="Heure", yaxis_title="Messages")
    return fig


def plot_bar(df: pd.DataFrame, x: str, y: str, title: str, orientation: str = "v"):
    if orientation == "h":
        plot_df = df.copy().iloc[::-1]
        fig = px.bar(plot_df, x=x, y=y, orientation="h", title=title)
    else:
        fig = px.bar(df, x=x, y=y, title=title)
    fig.update_layout(height=420)
    return fig


def plot_score(score: float):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=float(score),
        number={"suffix": "/100"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"thickness": 0.35},
            "steps": [
                {"range": [0, 40], "color": "rgba(0,180,90,0.18)"},
                {"range": [40, 60], "color": "rgba(255,200,0,0.20)"},
                {"range": [60, 80], "color": "rgba(255,120,0,0.22)"},
                {"range": [80, 100], "color": "rgba(255,0,0,0.20)"},
            ],
        },
        title={"text": "Crisis Velocity Score"},
    ))
    fig.update_layout(height=330, margin=dict(l=20, r=20, t=50, b=20))
    return fig


def mapping_editor(raw_df: pd.DataFrame, auto_mapping: Dict[str, Optional[str]]) -> Dict[str, Optional[str]]:
    st.markdown("### Mapping des colonnes")
    st.caption("L'app détecte les colonnes automatiquement. Corrige seulement si une colonne importante est mal reconnue.")
    columns = [None] + list(raw_df.columns)
    mapping = dict(auto_mapping)

    required = ["date", "author", "text"]
    optional = ["sentiment", "likes", "comments", "shares", "reach", "impressions", "engagement_type", "hashtags", "mentions", "followers", "text_norm", "repost_of"]

    cols = st.columns(3)
    for i, key in enumerate(required):
        current = mapping.get(key)
        idx = columns.index(current) if current in columns else 0
        mapping[key] = cols[i].selectbox(f"{key} *", columns, index=idx, key=f"map_{key}")

    with st.expander("Colonnes optionnelles", expanded=False):
        grid = st.columns(3)
        for i, key in enumerate(optional):
            current = mapping.get(key)
            idx = columns.index(current) if current in columns else 0
            mapping[key] = grid[i % 3].selectbox(key, columns, index=idx, key=f"map_{key}")
    return mapping


# -----------------------------------------------------------------------------
# Sidebar
# -----------------------------------------------------------------------------

st.sidebar.title("🚨 CrisisAI War Room")
st.sidebar.caption("Agent 1 — Analyste de crise virale")

uploaded = st.sidebar.file_uploader(
    "Importer le corpus X/Twitter",
    type=["csv", "xlsx", "xls"],
    help="Le fichier doit contenir au minimum une date, un auteur et un texte/message.",
)

st.sidebar.markdown("---")
st.sidebar.subheader("Réglages")
top_n = st.sidebar.slider("Nombre d'éléments dans les tops", 5, 30, 10)
show_mapping = st.sidebar.checkbox("Afficher/corriger le mapping", value=False)

st.sidebar.markdown("---")
st.sidebar.subheader("Brief LLM optionnel")
use_openrouter = st.sidebar.checkbox("Réécrire le brief avec OpenRouter", value=False)
openrouter_model = st.sidebar.text_input("Modèle OpenRouter", value=DEFAULT_MODEL)
openrouter_key_input = st.sidebar.text_input("Clé OpenRouter temporaire", type="password", value="")
st.sidebar.caption("Tu peux aussi définir OPENROUTER_API_KEY dans les secrets Streamlit.")


# -----------------------------------------------------------------------------
# Header
# -----------------------------------------------------------------------------

st.markdown('<div class="big-title">CrisisAI War Room — Agent 1</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Analyse descriptive automatique : pics, narratifs, acteurs, propagation et brief de crise.</div>', unsafe_allow_html=True)

if uploaded is None:
    st.markdown(
        """
        <div class="warning-box">
        <b>Commence ici :</b> importe ton fichier <code>data.xlsx</code> ou un CSV équivalent dans la barre latérale.
        L'application reproduira les résultats du notebook Agent 1, mais sous forme de dashboard Streamlit.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.info("Colonnes minimales attendues : date, auteur, texte. Les colonnes likes, shares, reach, sentiment, hashtags, type d'engagement sont utilisées si elles existent.")
    st.stop()

# Lecture raw pour mapping simple
file_bytes = uploaded.getvalue()
raw_preview = read_dataset(uploaded)
auto_mapping = auto_map_columns(raw_preview)

if show_mapping:
    mapping = mapping_editor(raw_preview, auto_mapping)
else:
    mapping = auto_mapping

try:
    with st.spinner("Nettoyage et enrichissement du corpus..."):
        # On repasse par bytes pour cache propre
        raw_df, df, used_mapping = cached_preprocess(file_bytes, uploaded.name, mapping)
except Exception as e:
    st.error(f"Impossible de préparer le corpus : {e}")
    with st.expander("Voir les colonnes détectées"):
        st.write(list(raw_preview.columns))
        st.json(auto_mapping)
    st.stop()

agent = AnalysteDeCrise(df)
daily = build_daily_timeline(df)
hourly = build_hourly_timeline(df)
peaks_d = detect_peaks_daily(df, n=10)
peaks_h = detect_peaks_hourly(df, n=20)
kpis = compute_kpis(df)

# -----------------------------------------------------------------------------
# KPIs globaux
# -----------------------------------------------------------------------------

c1, c2, c3, c4 = st.columns(4)
with c1:
    show_metric_card("Messages", format_int(kpis["messages"]), f"{format_int(kpis['auteurs_uniques'])} auteurs uniques")
with c2:
    show_metric_card("Retweets/Reposts", f"{kpis['retweets_pct']:.1f}%", f"{format_int(kpis['retweets'])} messages")
with c3:
    show_metric_card("Reach cumulé", format_int(kpis["reach"]), f"Impressions : {format_int(kpis['impressions'])}")
with c4:
    show_metric_card("Sentiment négatif", f"{kpis['sentiment_negatif_pct']:.1f}%", f"Risque moyen : {kpis['risk_moyen']:.2f}/5")

st.caption(f"Période couverte : {kpis['debut']} → {kpis['fin']}")

# -----------------------------------------------------------------------------
# Tabs
# -----------------------------------------------------------------------------

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Vue globale",
    "🔥 Pics détectés",
    "🤖 Agent 1 — Analyse période",
    "📦 Exports",
    "🎤 Démo / pitch",
])

with tab1:
    st.subheader("Vue globale du corpus")
    st.plotly_chart(plot_timeline_daily(daily), use_container_width=True)

    left, right = st.columns(2)
    with left:
        st.plotly_chart(plot_bar(engagement_type_table(df), x="type", y="count", title="Types d'engagement"), use_container_width=True)
    with right:
        st.plotly_chart(plot_bar(sentiment_table(df), x="sentiment", y="count", title="Sentiment"), use_container_width=True)

    left, right = st.columns(2)
    with left:
        st.plotly_chart(plot_bar(narratives_table(df).head(10), x="count", y="narrative", title="Narratifs dominants", orientation="h"), use_container_width=True)
    with right:
        hashtags = top_hashtags(df, n=10)
        if len(hashtags):
            st.plotly_chart(plot_bar(hashtags, x="count", y="hashtag", title="Top hashtags", orientation="h"), use_container_width=True)
        else:
            st.info("Aucun hashtag détecté.")

    with st.expander("Aperçu du corpus enrichi"):
        st.dataframe(df[["dt", "author", "engagement_type", "sentiment", "main_narrative", "risk_level", "text_raw"]].head(100), use_container_width=True)

with tab2:
    st.subheader("Pics automatiques")
    st.markdown("L'Agent 1 détecte les pics par volume et z-score. C'est la base pour choisir une période à analyser.")
    left, right = st.columns(2)
    with left:
        st.markdown("#### Top pics journaliers")
        st.dataframe(peaks_d, use_container_width=True)
    with right:
        st.markdown("#### Top pics horaires")
        st.dataframe(peaks_h, use_container_width=True)

    best_days = list(peaks_d["day"].head(2))
    focus = df[df["day"].isin(best_days)].copy()
    if len(focus):
        st.plotly_chart(plot_timeline_hourly(build_hourly_timeline(focus)), use_container_width=True)

with tab3:
    st.subheader("Agent 1 — Analyse d'une période")
    st.markdown("Choisis une période, puis l'agent produit un brief, des tops et des tableaux exploitables pour les slides.")

    min_dt, max_dt = df["dt"].min(), df["dt"].max()
    default_start = peaks_d.iloc[0]["day"].to_pydatetime() if len(peaks_d) else min_dt.to_pydatetime()
    default_end = default_start + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    default_end = min(default_end, max_dt.to_pydatetime())

    col_a, col_b, col_c = st.columns([1, 1, 1])
    with col_a:
        start_date = st.date_input("Date début", value=default_start.date(), min_value=min_dt.date(), max_value=max_dt.date())
        start_time = st.time_input("Heure début", value=time(0, 0))
    with col_b:
        end_date = st.date_input("Date fin", value=default_end.date(), min_value=min_dt.date(), max_value=max_dt.date())
        end_time = st.time_input("Heure fin", value=time(23, 59))
    with col_c:
        st.markdown("#### Raccourci")
        peak_rank = st.selectbox("Analyser le pic journalier n°", list(range(1, min(10, len(peaks_d)) + 1)), index=0)
        use_peak = st.button("Utiliser ce pic")

    if use_peak and len(peaks_d):
        result = agent.analyze_peak_day(rank=int(peak_rank), top_n=top_n)
    else:
        start = datetime.combine(start_date, start_time)
        end = datetime.combine(end_date, end_time)
        try:
            result = agent.analyze_period(start=start, end=end, top_n=top_n)
        except Exception as e:
            st.error(str(e))
            st.stop()

    score = result["crisis_velocity_score"]
    score_col, brief_col = st.columns([0.35, 0.65])
    with score_col:
        st.plotly_chart(plot_score(score), use_container_width=True)
        st.success(f"Niveau : {crisis_level(score)}")
    with brief_col:
        st.markdown(result["brief_deterministe"])

    if use_openrouter:
        api_key = openrouter_key_input or get_streamlit_secret("OPENROUTER_API_KEY", "")
        try:
            with st.spinner("Génération du brief OpenRouter..."):
                llm_brief = generate_openrouter_brief(result, api_key=api_key, model=openrouter_model)
            st.markdown("### Brief rédigé par LLM")
            st.markdown(llm_brief)
        except Exception as e:
            st.warning(f"Brief LLM indisponible. Brief déterministe conservé. Détail : {e}")

    st.markdown("---")
    left, right = st.columns(2)
    with left:
        st.markdown("#### Narratifs sur la période")
        st.dataframe(result["narratives"], use_container_width=True)
    with right:
        st.markdown("#### Top hashtags")
        st.dataframe(result["top_hashtags"], use_container_width=True)

    st.markdown("#### Top auteurs")
    st.dataframe(result["top_authors"], use_container_width=True)

    st.markdown("#### Top posts")
    st.dataframe(result["top_posts"], use_container_width=True)

    st.plotly_chart(plot_timeline_hourly(result["hourly_timeline"]), use_container_width=True)

    st.session_state["last_result"] = result

with tab4:
    st.subheader("Exports prêts pour slides / GitHub / Jour 3")
    if "last_result" not in st.session_state:
        st.info("Va d'abord dans l'onglet Agent 1 pour générer une analyse de période.")
    else:
        result = st.session_state["last_result"]
        files = result_to_export_files(result, df, prefix="agent1_streamlit")
        zip_bytes = make_zip(files)
        st.download_button(
            "⬇️ Télécharger tous les exports Agent 1 (.zip)",
            data=zip_bytes,
            file_name="exports_agent1_crisisai.zip",
            mime="application/zip",
        )
        st.markdown("Fichiers inclus :")
        st.write(sorted(files.keys()))

    st.markdown("#### Télécharger le corpus enrichi seul")
    enriched_cols = [
        "dt", "author", "engagement_type", "sentiment", "likes", "comments", "shares", "reach",
        "impressions", "is_retweet", "is_reply", "is_quote", "is_original", "main_narrative",
        "narratives", "risk_level", "text_raw", "text_norm",
    ]
    export_df = df[[c for c in enriched_cols if c in df.columns]].copy()
    export_df["narratives"] = export_df["narratives"].astype(str)
    st.download_button(
        "⬇️ Télécharger corpus_enrichi_agent1.csv",
        data=export_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
        file_name="corpus_enrichi_agent1.csv",
        mime="text/csv",
    )

with tab5:
    st.subheader("Démo orale prête pour l'animateur / jury")
    st.markdown(
        """
        ### Phrase d'ouverture
        > Nous avons transformé l'analyse Jour 1 en un Agent Analyste de crise. Il lit le corpus, détecte les pics, identifie les narratifs, les comptes moteurs et produit un brief directement exploitable par une cellule de communication.

        ### Démo recommandée
        1. Importer `data.xlsx`.
        2. Montrer les 4 KPIs : messages, retweets, reach, sentiment négatif.
        3. Ouvrir **Pics détectés** et montrer le pic principal.
        4. Ouvrir **Agent 1 — Analyse période** et analyser le 26–27 mars.
        5. Montrer le **Crisis Velocity Score**, le brief, les narratifs, les acteurs et les top posts.
        6. Terminer par les exports qui serviront à l'Agent 2 et au Jour 3.

        ### Message Top 1
        > Ce n'est pas un simple dashboard : c'est le premier module d'une War Room IA. L'Agent 1 observe et diagnostique. L'Agent 2 classera plus finement les narratifs. L'Agent 3 proposera la stratégie de réponse.
        """
    )

    st.markdown("### Limites à dire honnêtement")
    st.markdown(
        """
        - Les narratifs sont détectés ici par mots-clés : c'est volontairement interprétable et rapide pour le Jour 2.
        - On ne conclut pas à des bots : on parle seulement de dynamique d'amplification et de signaux faibles.
        - Les réponses doivent être validées par un humain avant publication.
        """
    )
