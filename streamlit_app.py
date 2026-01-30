import streamlit as st
from ddgs import DDGS
import pandas as pd

st.set_page_config(page_title="Leads Scoring Playground", layout="wide")
st.title("Leads Discovery + Scoring Playground")

st.sidebar.header("Scoring Weights (Playground)")

weights = {
    "base": st.sidebar.slider("Base score", 0.0, 3.0, 1.0, 0.1),

    "geo_query": st.sidebar.slider("Geography in QUERY (small boost)", 0.0, 1.0, 0.3, 0.1),
    "geo_text": st.sidebar.slider("Geography in TEXT (capped)", 0.0, 2.0, 1.0, 0.1),

    "identity_first": st.sidebar.slider("Identity (first hit)", 0.0, 3.0, 2.0, 0.1),
    "identity_repeat": st.sidebar.slider("Identity (repeat hit)", 0.0, 1.0, 0.3, 0.1),

    "behavior_per": st.sidebar.slider("Behavior (per hit)", 0.0, 1.0, 0.3, 0.1),

    "seniority_first": st.sidebar.slider("Seniority (first hit)", 0.0, 2.0, 1.5, 0.1),
    "seniority_repeat": st.sidebar.slider("Seniority (repeat hit)", 0.0, 1.0, 0.2, 0.1),
}

freeze_scoring = st.toggle("Freeze scoring", value=False)

identity_keywords = [
    "angel investor", "angel investing", "family office",
    "venture partner", "cio", "chief investment officer",
    "founder", "co-founder", "ceo"
]

behavior_keywords = [
    "invested in", "investing in", "portfolio",
    "seed", "pre-seed", "early-stage", "funding"
]

seniority_keywords = [
    "partner", "managing director", "chairman",
    "board member", "advisor", "advisory"
]

geo_keywords = ["uae", "dubai", "abu dhabi", "emirates", "mena", "middle east"]

def score_text(text, query, w):
    text = text.lower()
    query = query.lower()

    score = w["base"]
    signal_groups = set()
    breakdown = []

    geo_hit = False

    if any(k in query for k in geo_keywords):
        score += w["geo_query"]
        breakdown.append("Geography found in query")

    if any(k in text for k in geo_keywords):
        score += w["geo_text"]
        geo_hit = True
        breakdown.append("Geography found in text")

    if geo_hit:
        signal_groups.add("Geography")

    identity_hits = [k for k in identity_keywords if k in text]
    if identity_hits:
        score += w["identity_first"]
        score += max(0, len(identity_hits) - 1) * w["identity_repeat"]
        signal_groups.add("Identity")
        breakdown.append(f"Identity hits: {identity_hits}")

    behavior_hits = [k for k in behavior_keywords if k in text]
    if behavior_hits:
        score += len(behavior_hits) * w["behavior_per"]
        signal_groups.add("Behavior")
        breakdown.append(f"Behavior hits: {behavior_hits}")

    seniority_hits = [k for k in seniority_keywords if k in text]
    if seniority_hits:
        score += w["seniority_first"]
        score += max(0, len(seniority_hits) - 1) * w["seniority_repeat"]
        signal_groups.add("Seniority")
        breakdown.append(f"Seniority hits: {seniority_hits}")

    score = min(score, 10)

    group_count = len(signal_groups)
    if group_count >= 3:
        confidence = "High"
    elif group_count == 2:
        confidence = "Medium"
    else:
        confidence = "Low"

    breakdown.insert(0, f"Signal groups fired: {group_count}")

    return score, confidence, breakdown

st.subheader("Manual Scoring Playground")

sample_text = st.text_area(
    "Paste LinkedIn title + snippet",
    height=150,
    placeholder="Angel Investor | Based in Dubai | Investing in early-stage startups"
)

if sample_text:
    if freeze_scoring:
        score, confidence, breakdown = 0, "Manual", ["Scoring frozen"]
    else:
        score, confidence, breakdown = score_text(sample_text, "", weights)

    st.metric("Score (1–10)", score)
    st.metric("Confidence", confidence)

    with st.expander("Why this scored what it scored"):
        for b in breakdown:
            st.markdown(f"- {b}")
