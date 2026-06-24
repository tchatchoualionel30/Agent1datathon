# -*- coding: utf-8 -*-
"""
CrisisAI War Room — Agent 1 : Analyste de crise
=================================================
Ce module reprend la logique du notebook Agent 1 pour l'utiliser dans une app Streamlit.
Il accepte un corpus X/Twitter en CSV ou Excel, nettoie les données, détecte les pics,
classe rapidement les narratifs par mots-clés et produit un brief exploitable par une
cellule de communication de crise.
"""

from __future__ import annotations

import io
import json
import math
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple, Any

import numpy as np
import pandas as pd


# -----------------------------------------------------------------------------
# Normalisation et mapping colonnes
# -----------------------------------------------------------------------------

def strip_accents(s: Any) -> str:
    if pd.isna(s):
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFKD", str(s))
        if not unicodedata.combining(c)
    )


def norm_name(s: Any) -> str:
    s = strip_accents(str(s)).lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


COLUMN_CANDIDATES: Dict[str, List[str]] = {
    "date": ["Date", "datetime", "created_at", "post date", "postDate", "date_publication"],
    "url": ["Url", "URL", "link", "lien"],
    "sentiment": ["Sentiment", "sentiment_label", "tonalite"],
    "language": ["Language", "langue", "lang"],
    "country": ["Country", "pays"],
    "author": ["Author", "auteur", "username", "screen_name", "user", "compte"],
    "likes": ["Likes", "like_count", "likes_count", "nombre_likes"],
    "comments": ["Comments", "Replies", "reply_count", "comments_count", "reponses"],
    "shares": ["Shares", "Retweets", "retweet_count", "reposts", "partages"],
    "text": ["Full Text", "Text", "Tweet", "message", "content", "contenu", "texte"],
    "text_norm": ["message_normalizer", "message normalizer", "normalized_text", "texte_normalise", "text_norm"],
    "impressions": ["Impressions", "views", "vues"],
    "mentions": ["Mentioned Authors", "mentions", "mentioned_authors"],
    "followers": ["X Followers", "followers", "abonnes", "followers_count"],
    "following": ["X Following", "following", "abonnements"],
    "reply_to": ["X Reply to", "reply_to", "in_reply_to"],
    "repost_of": ["X Repost of", "repost_of", "retweeted_status", "retweeted_author"],
    "x_posts": ["X Posts", "statuses_count", "posts_count"],
    "verified": ["X Verified", "verified", "certified"],
    "reach": ["Reach", "audience", "portee"],
    "engagement_type": ["Engagement Type", "type", "interaction_type", "type_engagement"],
    "hashtags": ["Hashtags", "hashtags", "tags"],
    "post_id": ["postID", "post_id", "id", "tweet_id"],
    "post_date": ["postDate", "post_date"],
}

REQUIRED_COLUMNS = {"date", "author", "text"}


def find_col(columns: Iterable[str], possible_names: Iterable[str]) -> Optional[str]:
    original_columns = list(columns)
    normalized_to_original = {norm_name(c): c for c in original_columns}

    # Match exact après normalisation
    for name in possible_names:
        key = norm_name(name)
        if key in normalized_to_original:
            return normalized_to_original[key]

    # Match fuzzy très simple
    possible_keys = [norm_name(x) for x in possible_names]
    for key, original in normalized_to_original.items():
        if any(pk and (pk in key or key in pk) for pk in possible_keys):
            return original
    return None


def auto_map_columns(raw_df: pd.DataFrame) -> Dict[str, Optional[str]]:
    return {key: find_col(raw_df.columns, names) for key, names in COLUMN_CANDIDATES.items()}


def validate_mapping(mapping: Dict[str, Optional[str]]) -> Tuple[bool, List[str]]:
    missing = [k for k in REQUIRED_COLUMNS if not mapping.get(k)]
    return len(missing) == 0, missing


# -----------------------------------------------------------------------------
# Lecture fichier uploadé
# -----------------------------------------------------------------------------

def read_dataset(file_or_path: Any, sheet_name: Any = 0) -> pd.DataFrame:
    """Lit un CSV ou Excel depuis un chemin, un BytesIO ou un UploadedFile Streamlit."""
    name = getattr(file_or_path, "name", None) or str(file_or_path)
    lower = name.lower()

    if hasattr(file_or_path, "getvalue"):
        data = file_or_path.getvalue()
        buffer = io.BytesIO(data)
        if lower.endswith((".xlsx", ".xls")):
            return pd.read_excel(buffer, sheet_name=sheet_name)
        # CSV : tentative utf-8 puis latin-1
        try:
            return pd.read_csv(io.BytesIO(data))
        except UnicodeDecodeError:
            return pd.read_csv(io.BytesIO(data), encoding="latin-1", sep=None, engine="python")

    if lower.endswith((".xlsx", ".xls")):
        return pd.read_excel(file_or_path, sheet_name=sheet_name)
    try:
        return pd.read_csv(file_or_path)
    except UnicodeDecodeError:
        return pd.read_csv(file_or_path, encoding="latin-1", sep=None, engine="python")


# -----------------------------------------------------------------------------
# Narratifs Agent 1
# -----------------------------------------------------------------------------

NARRATIVE_KEYWORDS: Dict[str, List[str]] = {
    "Argent public / subventions": [
        r"argent public", r"subvention", r"subventionne", r"subventionnee", r"subventions",
        r"impot", r"impots", r"taxe", r"taxes", r"racket fiscal", r"vache a lait",
        r"fonds", r"finance", r"financer", r"financement", r"3 m", r"3m", r"millions",
    ],
    "Copinage / favoritisme": [
        r"copinage", r"favoritisme", r"favoriser", r"favorisera", r"potes", r"amis", r"proches",
        r"commission", r"corruption", r"clientelisme", r"entre soi", r"detournement",
    ],
    "Critique institutionnelle CNC": [
        r"\bcnc\b", r"centre national", r"institution", r"commission d aide", r"ministere", r"culture",
    ],
    "Ultia / Twitch": [
        r"ultia", r"twitch", r"streameuse", r"stream", r"live", r"youtube", r"tiktok",
    ],
    "Censure / idéologie": [
        r"censure", r"extreme droite", r"extreme-droite", r"ideologie", r"politique", r"gauche", r"droite",
        r"discrimination", r"ecarter", r"ecartera",
    ],
    "Suspension du fonds": [
        r"suspend", r"suspension", r"supprime", r"suppression", r"arrete le fonds", r"met fin", r"fonds d aide",
    ],
    "Harcèlement / menaces": [
        r"harcelement", r"cyberharcelement", r"menace", r"menaces", r"insulte", r"haine", r"violence",
    ],
    "Relais média / actualité": [
        r"flash", r"alerte", r"info", r"journal", r"media", r"article", r"communique", r"breaking",
    ],
}


# -----------------------------------------------------------------------------
# Prétraitement corpus
# -----------------------------------------------------------------------------

def preprocess_dataset(raw_df: pd.DataFrame, mapping: Optional[Dict[str, Optional[str]]] = None) -> Tuple[pd.DataFrame, Dict[str, Optional[str]]]:
    """Nettoie le corpus et ajoute les colonnes nécessaires à l'Agent 1."""
    if mapping is None:
        mapping = auto_map_columns(raw_df)
    ok, missing = validate_mapping(mapping)
    if not ok:
        raise ValueError(
            "Colonnes obligatoires introuvables : " + ", ".join(missing) +
            ". Corrigez le mapping dans l'application."
        )

    df = raw_df.copy()

    # Date
    date_col = mapping["date"]
    df["dt"] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=["dt"]).copy()
    if len(df) == 0:
        raise ValueError("Aucune date valide trouvée dans la colonne sélectionnée.")
    df["date"] = df["dt"].dt.date
    df["day"] = df["dt"].dt.floor("D")
    df["hour"] = df["dt"].dt.floor("h")
    df["hour_of_day"] = df["dt"].dt.hour
    df["week"] = df["dt"].dt.to_period("W").astype(str)

    # Texte
    text_col = mapping["text"]
    text_norm_col = mapping.get("text_norm") or text_col
    df["text_raw"] = df[text_col].fillna("").astype(str)
    if text_norm_col in df.columns:
        df["text_norm"] = df[text_norm_col].fillna(df["text_raw"]).astype(str).map(lambda x: strip_accents(x).lower())
    else:
        df["text_norm"] = df["text_raw"].astype(str).map(lambda x: strip_accents(x).lower())

    # Auteur
    author_col = mapping["author"]
    df["author"] = df[author_col].fillna("unknown").astype(str).str.strip().str.lstrip("@")
    df.loc[df["author"].eq(""), "author"] = "unknown"

    # Numériques
    for new_col, src in {
        "likes": mapping.get("likes"),
        "comments": mapping.get("comments"),
        "shares": mapping.get("shares"),
        "impressions": mapping.get("impressions"),
        "reach": mapping.get("reach"),
        "followers": mapping.get("followers"),
        "following": mapping.get("following"),
        "x_posts": mapping.get("x_posts"),
    }.items():
        if src and src in df.columns:
            df[new_col] = pd.to_numeric(df[src], errors="coerce").fillna(0)
        else:
            df[new_col] = 0

    df["engagement_total"] = df["likes"] + df["comments"] + df["shares"]

    # Type engagement
    engagement_type_col = mapping.get("engagement_type")
    if engagement_type_col and engagement_type_col in df.columns:
        df["engagement_type"] = df[engagement_type_col].fillna("ORIGINAL").astype(str).str.upper().str.strip()
    else:
        df["engagement_type"] = "ORIGINAL"

    repost_col = mapping.get("repost_of")
    has_repost_of = df[repost_col].notna() if repost_col and repost_col in df.columns else False
    df["is_retweet"] = (
        df["engagement_type"].str.contains("RETWEET|REPOST|RT", regex=True, na=False)
        | has_repost_of
        | df["text_raw"].str.startswith("RT ")
    )
    df["is_reply"] = df["engagement_type"].str.contains("REPLY|REPONSE|RÉPONSE", regex=True, na=False)
    df["is_quote"] = df["engagement_type"].str.contains("QUOTE|CITATION", regex=True, na=False)
    df["is_original"] = ~(df["is_retweet"] | df["is_reply"] | df["is_quote"])

    # Sentiment
    sentiment_col = mapping.get("sentiment")
    if sentiment_col and sentiment_col in df.columns:
        df["sentiment"] = df[sentiment_col].fillna("unknown").astype(str).str.lower().str.strip()
    else:
        df["sentiment"] = "unknown"

    # Hashtags / mentions
    hashtag_col = mapping.get("hashtags")
    mention_col = mapping.get("mentions")

    def extract_hashtags(row: pd.Series) -> List[str]:
        tags: List[str] = []
        if hashtag_col and hashtag_col in row.index and pd.notna(row.get(hashtag_col, np.nan)):
            tags += re.findall(r"#\w+", str(row[hashtag_col]).lower())
        tags += re.findall(r"#\w+", str(row["text_raw"]).lower())
        return sorted(set(tags))

    def extract_mentions(row: pd.Series) -> List[str]:
        mentions: List[str] = []
        if mention_col and mention_col in row.index and pd.notna(row.get(mention_col, np.nan)):
            mentions += re.findall(r"@\w+", str(row[mention_col]).lower())
        mentions += re.findall(r"@\w+", str(row["text_raw"]).lower())
        return sorted(set(mentions))

    df["hashtags_list"] = df.apply(extract_hashtags, axis=1)
    df["hashtags_joined"] = df["hashtags_list"].apply(lambda x: " ".join(x))
    df["mentions_list"] = df.apply(extract_mentions, axis=1)

    # Narratifs vectorisés
    narrative_flag_cols: List[Tuple[str, str]] = []
    for narrative, patterns in NARRATIVE_KEYWORDS.items():
        pattern = "|".join(f"(?:{p})" for p in patterns)
        col = "narr_" + norm_name(narrative)
        df[col] = df["text_norm"].str.contains(pattern, regex=True, case=False, na=False)
        narrative_flag_cols.append((narrative, col))

    def flags_to_narratives(row: pd.Series) -> List[str]:
        tags = [narr for narr, col in narrative_flag_cols if bool(row[col])]
        return tags if tags else ["Autre / non classé"]

    df["narratives"] = df.apply(flags_to_narratives, axis=1)
    df["main_narrative"] = df["narratives"].apply(lambda x: x[0] if x else "Autre / non classé")

    # Risque message approximatif
    sensitive_tags = {
        "Copinage / favoritisme",
        "Argent public / subventions",
        "Censure / idéologie",
        "Harcèlement / menaces",
        "Suspension du fonds",
    }
    reach_p95 = df["reach"].quantile(0.95) if "reach" in df else 0

    def message_risk(row: pd.Series) -> int:
        score = 1.0
        tags = set(row["narratives"])
        score += len(tags & sensitive_tags)
        if str(row["sentiment"]).lower() in ["negative", "negatif", "négatif", "neg"]:
            score += 1
        if bool(row["is_retweet"]):
            score += 0.5
        if reach_p95 and row["reach"] >= reach_p95:
            score += 1
        return int(min(5, max(1, round(score))))

    df["risk_level"] = df.apply(message_risk, axis=1)
    return df, mapping


# -----------------------------------------------------------------------------
# Calculs Agent 1
# -----------------------------------------------------------------------------

def pct(x: float, total: float) -> float:
    return 0.0 if total == 0 else 100.0 * float(x) / float(total)


def safe_sum(s: pd.Series) -> float:
    return float(pd.to_numeric(s, errors="coerce").fillna(0).sum())


def format_int(x: Any) -> str:
    try:
        return f"{int(round(float(x))):,}".replace(",", " ")
    except Exception:
        return str(x)


def compute_kpis(data: pd.DataFrame) -> Dict[str, Any]:
    total = len(data)
    if total == 0:
        return {}
    return {
        "messages": int(total),
        "auteurs_uniques": int(data["author"].nunique()),
        "debut": str(data["dt"].min()),
        "fin": str(data["dt"].max()),
        "retweets": int(data["is_retweet"].sum()),
        "retweets_pct": pct(data["is_retweet"].sum(), total),
        "originaux": int(data["is_original"].sum()),
        "originaux_pct": pct(data["is_original"].sum(), total),
        "reponses": int(data["is_reply"].sum()),
        "citations": int(data["is_quote"].sum()),
        "likes": safe_sum(data["likes"]),
        "comments": safe_sum(data["comments"]),
        "shares": safe_sum(data["shares"]),
        "impressions": safe_sum(data["impressions"]),
        "reach": safe_sum(data["reach"]),
        "engagement_total": safe_sum(data["engagement_total"]),
        "sentiment_negatif_pct": pct(data["sentiment"].isin(["negative", "negatif", "négatif", "neg"]).sum(), total),
        "risk_moyen": float(data["risk_level"].mean()),
        "risk_max": int(data["risk_level"].max()),
    }


def top_authors(data: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    agg = data.groupby("author", dropna=False).agg(
        messages=("author", "size"),
        retweets=("is_retweet", "sum"),
        likes=("likes", "sum"),
        shares=("shares", "sum"),
        reach=("reach", "sum"),
        impressions=("impressions", "sum"),
        followers=("followers", "max"),
        risk_mean=("risk_level", "mean"),
    ).reset_index()
    agg["influence_score"] = (
        np.log1p(agg["reach"]) * 0.35
        + np.log1p(agg["shares"]) * 0.25
        + np.log1p(agg["likes"]) * 0.20
        + np.log1p(agg["messages"]) * 0.10
        + np.log1p(agg["followers"]) * 0.10
    )
    return agg.sort_values(["influence_score", "reach", "shares"], ascending=False).head(n)


def top_hashtags(data: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    tags: List[str] = []
    for lst in data.get("hashtags_list", []):
        if isinstance(lst, list):
            tags.extend(lst)
    if not tags:
        return pd.DataFrame(columns=["hashtag", "count"])
    return pd.Series(tags).value_counts().rename_axis("hashtag").reset_index(name="count").head(n)


def top_posts(data: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    cols = [
        "dt", "author", "engagement_type", "sentiment", "likes", "comments", "shares",
        "reach", "risk_level", "main_narrative", "text_raw"
    ]
    cols = [c for c in cols if c in data.columns]
    return data.sort_values(["engagement_total", "reach", "shares"], ascending=False)[cols].head(n)


def narratives_table(data: pd.DataFrame) -> pd.DataFrame:
    rows: List[str] = []
    for tags in data.get("narratives", []):
        if isinstance(tags, list):
            rows.extend(tags)
    if not rows:
        return pd.DataFrame(columns=["narrative", "count", "pct_messages"])
    tab = pd.Series(rows).value_counts().rename_axis("narrative").reset_index(name="count")
    tab["pct_messages"] = tab["count"] / max(1, len(data)) * 100
    return tab


def sentiment_table(data: pd.DataFrame) -> pd.DataFrame:
    if len(data) == 0:
        return pd.DataFrame(columns=["sentiment", "count", "pct"])
    tab = data["sentiment"].value_counts(dropna=False).rename_axis("sentiment").reset_index(name="count")
    tab["pct"] = tab["count"] / len(data) * 100
    return tab


def engagement_type_table(data: pd.DataFrame) -> pd.DataFrame:
    if len(data) == 0:
        return pd.DataFrame(columns=["type", "count", "pct"])
    tab = data["engagement_type"].fillna("ORIGINAL").value_counts().rename_axis("type").reset_index(name="count")
    tab["pct"] = tab["count"] / len(data) * 100
    return tab


def build_daily_timeline(data: pd.DataFrame) -> pd.DataFrame:
    if len(data) == 0:
        return pd.DataFrame(columns=["day", "messages", "auteurs", "retweets", "reach", "impressions", "engagement", "risk_mean", "retweets_pct", "rolling_mean_3d", "zscore"])
    tl = data.groupby("day").agg(
        messages=("author", "size"),
        auteurs=("author", "nunique"),
        retweets=("is_retweet", "sum"),
        reach=("reach", "sum"),
        impressions=("impressions", "sum"),
        engagement=("engagement_total", "sum"),
        risk_mean=("risk_level", "mean"),
    ).reset_index().sort_values("day")
    tl["retweets_pct"] = np.where(tl["messages"] > 0, tl["retweets"] / tl["messages"] * 100, 0)
    tl["rolling_mean_3d"] = tl["messages"].rolling(3, min_periods=1).mean()
    tl["zscore"] = (tl["messages"] - tl["messages"].mean()) / (tl["messages"].std(ddof=0) + 1e-9)
    return tl


def build_hourly_timeline(data: pd.DataFrame) -> pd.DataFrame:
    if len(data) == 0:
        return pd.DataFrame(columns=["hour", "messages", "auteurs", "retweets", "reach", "impressions", "engagement", "risk_mean", "retweets_pct", "rolling_mean_6h", "zscore"])
    tl = data.groupby("hour").agg(
        messages=("author", "size"),
        auteurs=("author", "nunique"),
        retweets=("is_retweet", "sum"),
        reach=("reach", "sum"),
        impressions=("impressions", "sum"),
        engagement=("engagement_total", "sum"),
        risk_mean=("risk_level", "mean"),
    ).reset_index().sort_values("hour")
    tl["retweets_pct"] = np.where(tl["messages"] > 0, tl["retweets"] / tl["messages"] * 100, 0)
    tl["rolling_mean_6h"] = tl["messages"].rolling(6, min_periods=1).mean()
    tl["zscore"] = (tl["messages"] - tl["messages"].mean()) / (tl["messages"].std(ddof=0) + 1e-9)
    return tl


def detect_peaks_daily(data: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    return build_daily_timeline(data).sort_values(["messages", "zscore"], ascending=False).head(n).copy()


def detect_peaks_hourly(data: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    return build_hourly_timeline(data).sort_values(["messages", "zscore"], ascending=False).head(n).copy()


def crisis_velocity_score(period_data: pd.DataFrame, reference_data: pd.DataFrame) -> float:
    """Score 0-100 : volume, vitesse, reach, négativité, risque et retweets."""
    if len(period_data) == 0:
        return 0.0
    k = compute_kpis(period_data)
    period_hours = max(1.0, (period_data["dt"].max() - period_data["dt"].min()).total_seconds() / 3600.0)
    ref_hours = max(1.0, (reference_data["dt"].max() - reference_data["dt"].min()).total_seconds() / 3600.0)
    volume_per_hour = len(period_data) / period_hours
    ref_volume_per_hour = len(reference_data) / ref_hours

    volume_component = min(30.0, 10.0 * math.log1p(volume_per_hour / (ref_volume_per_hour + 1e-9)))
    reach_total_ref = reference_data["reach"].sum() if "reach" in reference_data.columns else 0
    reach_component = min(20.0, 20.0 * (np.log1p(k["reach"]) / np.log1p(reach_total_ref + 1))) if reach_total_ref > 0 else 0.0
    negativity_component = min(15.0, k["sentiment_negatif_pct"] / 100.0 * 15.0)
    rt_component = min(15.0, k["retweets_pct"] / 100.0 * 15.0)
    risk_component = min(20.0, (k["risk_moyen"] / 5.0) * 20.0)
    return round(volume_component + reach_component + negativity_component + rt_component + risk_component, 1)


def crisis_level(score: float) -> str:
    if score >= 80:
        return "CRISE FORTE"
    if score >= 60:
        return "CRISE ÉLEVÉE"
    if score >= 40:
        return "CRISE MODÉRÉE"
    return "SIGNAL FAIBLE / BRUIT"


# -----------------------------------------------------------------------------
# Classe Agent 1
# -----------------------------------------------------------------------------

@dataclass
class AnalysteDeCrise:
    df: pd.DataFrame

    def __post_init__(self) -> None:
        self.df = self.df.copy()
        self.daily = build_daily_timeline(self.df)
        self.hourly = build_hourly_timeline(self.df)

    def filter_period(self, start: Optional[Any] = None, end: Optional[Any] = None) -> pd.DataFrame:
        data = self.df.copy()
        if start is not None:
            data = data[data["dt"] >= pd.to_datetime(start)]
        if end is not None:
            data = data[data["dt"] <= pd.to_datetime(end)]
        return data.copy()

    def analyze_period(self, start: Optional[Any] = None, end: Optional[Any] = None, top_n: int = 10) -> Dict[str, Any]:
        data = self.filter_period(start, end)
        if len(data) == 0:
            raise ValueError("Aucun message dans cette période.")
        result: Dict[str, Any] = {
            "periode": {"start": str(data["dt"].min()), "end": str(data["dt"].max())},
            "kpis": compute_kpis(data),
            "crisis_velocity_score": crisis_velocity_score(data, self.df),
            "top_authors": top_authors(data, n=top_n),
            "top_hashtags": top_hashtags(data, n=top_n),
            "top_posts": top_posts(data, n=top_n),
            "narratives": narratives_table(data),
            "sentiments": sentiment_table(data),
            "engagement_types": engagement_type_table(data),
            "hourly_timeline": build_hourly_timeline(data),
            "period_data": data,
        }
        result["brief_deterministe"] = build_deterministic_brief(result)
        return result

    def analyze_peak_day(self, rank: int = 1, top_n: int = 10) -> Dict[str, Any]:
        peaks = self.daily.sort_values(["messages", "zscore"], ascending=False).reset_index(drop=True)
        if rank < 1 or rank > len(peaks):
            raise ValueError("Rang de pic invalide.")
        day = peaks.loc[rank - 1, "day"]
        start = pd.to_datetime(day)
        end = start + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        return self.analyze_period(start=start, end=end, top_n=top_n)


def build_deterministic_brief(result: Dict[str, Any]) -> str:
    k = result["kpis"]
    score = result["crisis_velocity_score"]
    narr = result["narratives"].head(5)
    sent = result["sentiments"]
    top_a = result["top_authors"].head(5)

    dominant_narrative = narr.iloc[0]["narrative"] if len(narr) else "non identifié"
    dominant_sent = sent.iloc[0]["sentiment"] if len(sent) else "unknown"
    top_author = top_a.iloc[0]["author"] if len(top_a) else "non identifié"
    level = crisis_level(score)

    lines: List[str] = []
    lines.append("## Brief Agent 1 — Analyste de crise")
    lines.append("")
    lines.append(f"**Période analysée :** {result['periode']['start']} → {result['periode']['end']}")
    lines.append(f"**Niveau estimé :** {level}")
    lines.append(f"**Crisis Velocity Score :** {score}/100")
    lines.append("")
    lines.append("### 1. Chiffres clés")
    lines.append(f"- {format_int(k['messages'])} messages publiés par {format_int(k['auteurs_uniques'])} auteurs uniques.")
    lines.append(f"- {k['retweets_pct']:.1f}% de retweets/reposts : la crise fonctionne surtout par amplification.")
    lines.append(f"- Reach cumulé estimé : {format_int(k['reach'])} ; impressions : {format_int(k['impressions'])}.")
    lines.append(f"- Sentiment négatif : {k['sentiment_negatif_pct']:.1f}% ; risque moyen : {k['risk_moyen']:.2f}/5.")
    lines.append("")
    lines.append("### 2. Narratif dominant")
    lines.append(f"- Narratif principal détecté : **{dominant_narrative}**.")
    for _, row in narr.iterrows():
        lines.append(f"- {row['narrative']} : {format_int(row['count'])} occurrences ({row['pct_messages']:.1f}% des messages).")
    lines.append("")
    lines.append("### 3. Acteurs et amplification")
    lines.append(f"- Compte le plus influent sur la période : **@{top_author}** selon le score d'influence calculé.")
    for _, row in top_a.iterrows():
        lines.append(f"- @{row['author']} : {format_int(row['messages'])} messages, reach {format_int(row['reach'])}, shares {format_int(row['shares'])}.")
    lines.append("")
    lines.append("### 4. Lecture stratégique")
    lines.append("- Le sujet doit être traité comme une **dynamique virale**, pas comme une simple vérification de fake news.")
    lines.append("- Le point à surveiller est la mutation du débat : personne impliquée → institution → argent public / légitimité du fonds.")
    lines.append("- La cellule de crise doit répondre sur les règles, la transparence et les faits, sans entrer dans un affrontement politique.")
    if str(dominant_sent).lower() in ["negative", "negatif", "négatif", "neg"]:
        lines.append("- Le climat dominant étant négatif, la réponse doit éviter toute formulation défensive ou agressive.")
    return "\n".join(lines)


def result_to_export_files(result: Dict[str, Any], df: pd.DataFrame, prefix: str = "agent1_analyse") -> Dict[str, bytes]:
    """Prépare les CSV/Markdown à télécharger depuis Streamlit."""
    files: Dict[str, bytes] = {}
    files[f"{prefix}_rapport.md"] = result["brief_deterministe"].encode("utf-8")

    for key, filename in [
        ("top_authors", f"{prefix}_top_authors.csv"),
        ("top_hashtags", f"{prefix}_top_hashtags.csv"),
        ("top_posts", f"{prefix}_top_posts.csv"),
        ("narratives", f"{prefix}_narratives.csv"),
        ("hourly_timeline", f"{prefix}_hourly_timeline.csv"),
    ]:
        files[filename] = result[key].to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

    global_files = {
        "timeline_journaliere.csv": build_daily_timeline(df),
        "timeline_horaire.csv": build_hourly_timeline(df),
        "pics_journaliers_detectes.csv": detect_peaks_daily(df),
        "pics_horaires_detectes.csv": detect_peaks_hourly(df),
        "narratifs_globaux.csv": narratives_table(df),
        "top_50_auteurs_influence.csv": top_authors(df, n=50),
        "top_50_hashtags.csv": top_hashtags(df, n=50),
    }
    for name, table in global_files.items():
        files[name] = table.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

    cols_export = [
        "dt", "author", "engagement_type", "sentiment", "likes", "comments", "shares", "reach",
        "impressions", "is_retweet", "is_reply", "is_quote", "is_original", "main_narrative",
        "narratives", "risk_level", "text_raw", "text_norm",
    ]
    export_df = df[[c for c in cols_export if c in df.columns]].copy()
    export_df["narratives"] = export_df["narratives"].astype(str)
    files["corpus_enrichi_agent1.csv"] = export_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    return files


def make_zip(files: Dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    buffer.seek(0)
    return buffer.getvalue()


def result_context_json(result: Dict[str, Any], max_posts: int = 5) -> str:
    """Contexte JSON court pour un LLM externe éventuel."""
    posts = result["top_posts"].head(max_posts).copy()
    if "dt" in posts.columns:
        posts["dt"] = posts["dt"].astype(str)
    context = {
        "periode": result["periode"],
        "kpis": result["kpis"],
        "crisis_velocity_score": result["crisis_velocity_score"],
        "niveau": crisis_level(result["crisis_velocity_score"]),
        "narratifs": result["narratives"].head(8).to_dict(orient="records"),
        "top_auteurs": result["top_authors"].head(8).to_dict(orient="records"),
        "top_posts": posts.to_dict(orient="records"),
    }
    return json.dumps(context, ensure_ascii=False, indent=2, default=str)
