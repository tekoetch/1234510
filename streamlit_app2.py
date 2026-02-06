import streamlit as st
from ddgs import DDGS
import pandas as pd
import re

if "results" not in st.session_state:
    st.session_state.results = []

st.set_page_config(page_title="Leads Dashboard", layout="wide")
st.title("Leads Discovery")

freeze_scoring = st.toggle("Freeze scoring (manual)", value=False)

st.sidebar.header("Scoring Controls")

BASE_SCORE = st.sidebar.slider("Base score (query baseline)", 0.0, 3.0, 1.5, 0.1)
IDENTITY_WEIGHT = st.sidebar.slider("Primary identity boost", 0.5, 3.0, 1.8, 0.1)
IDENTITY_DIMINISHING_WEIGHT = st.sidebar.slider("Additional identity boost", 0.2, 1.5, 0.8, 0.1)
BEHAVIOR_WEIGHT = st.sidebar.slider("Behavior keyword boost", 0.1, 2.0, 0.4, 0.1)
BEHAVIOR_GROUP_BONUS = st.sidebar.slider("Identity + behavior synergy bonus", 0.0, 1.0, 0.5, 0.1)
SENIORITY_WEIGHT = st.sidebar.slider("Seniority keyword boost", 0.2, 3.0, 1.0, 0.1)
SENIORITY_GROUP_BONUS = st.sidebar.slider("Seniority group bonus", 0.0, 1.0, 0.5, 0.1)
GEO_GROUP_BONUS = st.sidebar.slider("Geography group bonus", 0.0, 1.0, 0.5, 0.1)

identity_keywords = [
    "angel investor", "angel investing", "family office",
    "venture partner", "chief investment officer", "cio",
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

uae_keywords = ["uae", "dubai", "abu dhabi", "emirates"]
mena_keywords = ["mena", "middle east", "gulf"]

blocked_urls = [
    "bing.com/aclick",
    "bing.com/ck/a",
    "doubleclick.net"
]

QUERY_BLOCKLIST = {"partner", "ceo", "co-founder"}

def normalize_url(url):
    return url.split("?")[0].lower().strip()

def score_text(text, query, url=""):
    text = text.lower()
    score = BASE_SCORE
    breakdown = []
    signal_groups = set()

    identity_hits = [k for k in identity_keywords if k in text]
    if identity_hits:
        score += IDENTITY_WEIGHT
        breakdown.append(f"Primary identity '{identity_hits[0]}' (+{IDENTITY_WEIGHT})")
        for k in identity_hits[1:]:
            score += IDENTITY_DIMINISHING_WEIGHT
            breakdown.append(f"Additional identity '{k}' (+{IDENTITY_DIMINISHING_WEIGHT})")
        signal_groups.add("Identity")

    behavior_hits = [k for k in behavior_keywords if k in text]
    for k in behavior_hits:
        score += BEHAVIOR_WEIGHT
        breakdown.append(f"Behavior keyword '{k}' (+{BEHAVIOR_WEIGHT})")

    if behavior_hits and "Identity" in signal_groups:
        score += BEHAVIOR_GROUP_BONUS
        breakdown.append(f"Identity + behavior synergy (+{BEHAVIOR_GROUP_BONUS})")
        signal_groups.add("Behavior")

    seniority_hits = [k for k in seniority_keywords if k in text]
    for k in seniority_hits:
        score += SENIORITY_WEIGHT
        breakdown.append(f"Seniority keyword '{k}' (+{SENIORITY_WEIGHT})")

    if seniority_hits:
        score += SENIORITY_GROUP_BONUS
        breakdown.append(f"Seniority group bonus (+{SENIORITY_GROUP_BONUS})")
        signal_groups.add("Seniority")

    if any(k in text for k in uae_keywords + mena_keywords):
        signal_groups.add("Geography")
        score += GEO_GROUP_BONUS
        breakdown.append(f"Geography group bonus (+{GEO_GROUP_BONUS})")

    score = min(score, 10.0)
    confidence = "High" if len(signal_groups) >= 3 else "Medium" if len(signal_groups) == 2 else "Low"
    breakdown.insert(0, f"Signal groups fired: {len(signal_groups)}")

    return score, confidence, breakdown

def is_valid_person_name(name):
    if not name or len(name.split()) < 2:
        return False
    if name.lower() == "angel investor":
        return False
    return True

st.subheader("Public Lead Discovery")

query_input = st.text_area(
    "Enter one search query per line",
    height=120,
    placeholder='"angel investor" UAE site:linkedin.com/in'
)

max_results_per_query = st.number_input(
    "Results per query",
    min_value=1,
    max_value=50,
    value=10,
    step=1
)

if st.button("Run Discovery") and query_input.strip():
    queries = [q.strip() for q in query_input.split("\n") if q.strip()]

    with DDGS(timeout=10) as ddgs:
        for query in queries:
            for r in ddgs.text(query, max_results=max_results_per_query, backend="lite"):
                title = r.get("title", "")
                snippet = r.get("body", "")
                url = r.get("href", "")

                if not url:
                    continue

                if any(bad in normalize_url(url) for bad in blocked_urls):
                    continue

                combined = f"{title} {snippet}"
                score, conf, breakdown = score_text(combined, query, url)
                name = title.split("-")[0].strip()

                if not is_valid_person_name(name):
                    continue

                st.session_state.results.append({
                    "Reviewed": False,
                    "Name": name,
                    "Title": title,
                    "Snippet": snippet,
                    "URL": url,
                    "Score": score,
                    "Confidence": conf,
                    "Signals": " | ".join(breakdown)
                })

EXPECTED_COLUMNS = [
    "Reviewed", "Name", "Title", "Snippet",
    "URL", "Score", "Confidence", "Signals"
]

df_first = pd.DataFrame(st.session_state.results)

for col in EXPECTED_COLUMNS:
    if col not in df_first.columns:
        df_first[col] = []

st.dataframe(
    df_first[["Reviewed", "Name", "Score", "Confidence", "Signals", "Snippet", "URL"]],
    use_container_width=True
)
