import streamlit as st
from ddgs import DDGS
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import re

if "results" not in st.session_state:
    st.session_state.results = []

st.set_page_config(page_title="Leads Dashboard + Scoring Playground", layout="wide")
st.title("Leads Discovery + Scoring Playground")

Scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_info = st.secrets["GCP_SERVICE_ACCOUNT_JSON"]
credentials = Credentials.from_service_account_info(creds_info, scopes=Scopes)
gc = gspread.authorize(credentials)

freeze_scoring = st.toggle("Freeze scoring (manual review mode)", value=False)

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
    "seed", "pre-seed", "early-stage", "funding", "fundraising"
]

seniority_keywords = [
    "partner", "managing director", "chairman",
    "board member", "advisor", "advisory"
]

uae_keywords = ["uae", "dubai", "abu dhabi", "emirates"]
mena_keywords = ["mena", "middle east", "gulf"]

def url_origin_bonus(url):
    u = url.lower()
    if u.startswith("https://ae.linkedin.com"):
        return 0.4
    if u.startswith("https://qa.linkedin.com"):
        return 0.1
    if u.startswith("https://in.linkedin.com"):
        return 0.0
    return 0.0

def normalize_url(url):
    return url.split("?")[0].lower().strip()

def score_text(text, query, url=""):
    text = text.lower()
    query = query.lower()

    location_match = re.search(r"location:\s*([^\n|·]+)", text)
    if location_match:
        loc = location_match.group(1)
        if not any(k in loc for k in uae_keywords + mena_keywords):
            return 0.0, "Low", ["Hard reject: explicit non-UAE/MENA location"]

    score = BASE_SCORE
    breakdown = [f"Base score from query (+{BASE_SCORE})"]
    signal_groups = set()

    if any(k in query for k in uae_keywords):
        score += 0.3
        breakdown.append("UAE mentioned in query (+0.3)")

    if any(k in query for k in mena_keywords):
        score += 0.2
        breakdown.append("MENA mentioned in query (+0.2)")

    if any(k in text for k in uae_keywords):
        score += 1.0
        signal_groups.add("Geography")
        breakdown.append("UAE mentioned in text (+1.0)")
    elif any(k in text for k in mena_keywords):
        score += 0.6
        signal_groups.add("Geography")
        breakdown.append("MENA mentioned in text (+0.6)")

    origin_bonus = url_origin_bonus(url)
    if origin_bonus > 0:
        score += origin_bonus
        breakdown.append(f"URL origin bonus (+{origin_bonus})")
        signal_groups.add("Geography")

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

    if "Geography" in signal_groups:
        score += GEO_GROUP_BONUS
        breakdown.append(f"Geography group bonus (+{GEO_GROUP_BONUS})")

    score = min(score, 10.0)
    group_count = len(signal_groups)
    confidence = "High" if group_count >= 3 else "Medium" if group_count == 2 else "Low"
    breakdown.insert(0, f"Signal groups fired: {group_count}")
    return score, confidence, breakdown

st.subheader("Manual Scoring Playground")

sample_text = st.text_area(
    "Paste LinkedIn title + snippet",
    height=150,
    placeholder="Angel Investor | Based in Dubai | Investing in early-stage startups"
)

if sample_text:
    score, confidence, breakdown = score_text(sample_text, "")
    st.metric("Score (1–10)", score)
    st.metric("Confidence", confidence)
    with st.expander("Why this scored what it scored"):
        for b in breakdown:
            st.write(b)

queries = [
    'angel investor dubai united arab emirates uae site:linkedin.com/in'
]

st.subheader("Live Discovery")

if st.button("Run Discovery"):
    with DDGS(timeout=10) as ddgs:
        for query in queries:
            for r in ddgs.text(query, max_results=5, backend="html"):
                title = r.get("title", "")
                snippet = r.get("body", "")
                url = r.get("href", "")
                if not url:
                    continue

                norm_url = normalize_url(url)
                existing_urls = {normalize_url(r["URL"]) for r in st.session_state.results}
                if norm_url in existing_urls:
                    continue

                combined_text = f"{title} {snippet}"
                score, confidence, breakdown = score_text(combined_text, query, url)

                st.session_state.results.append({
                    "Title": title,
                    "Snippet": snippet,
                    "URL": url,
                    "Score": score,
                    "Confidence": confidence,
                    "Signals": " | ".join(breakdown)
                })

    df = pd.DataFrame(st.session_state.results)
    st.dataframe(df, use_container_width=True)

    sh = gc.open_by_url("https://docs.google.com/spreadsheets/d/13syl6pUSdsXQ1XNnN_WVCGlpWm-80n6at4pdjZSuoBU/edit#gid=0")
    ws = sh.sheet1

    headers = ["Title", "Snippet", "URL", "Score", "Confidence", "Signals"]
    if ws.row_count == 0 or ws.row_values(1) != headers:
        ws.clear()
        ws.append_row(headers)

    sheet_urls = {
        normalize_url(r["URL"])
        for r in ws.get_all_records()
        if r.get("URL")
    }

    rows_to_add = []
    for _, row in df.iterrows():
        if normalize_url(row["URL"]) not in sheet_urls:
            rows_to_add.append([
                row["Title"],
                row["Snippet"],
                row["URL"],
                row["Score"],
                row["Confidence"],
                row["Signals"]
            ])

    if rows_to_add:
        ws.append_rows(rows_to_add, value_input_option="RAW")
