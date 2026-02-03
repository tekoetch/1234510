import streamlit as st
from ddgs import DDGS
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import re

if "results" not in st.session_state:
    st.session_state.results = []

if "second_pass_results" not in st.session_state:
    st.session_state.second_pass_results = []

st.set_page_config(page_title="Leads Dashboard + Scoring Playground", layout="wide")
st.title("Leads Discovery + Scoring Playground")

Scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# ---- GOOGLE SHEETS (PRESERVED, COMMENTED OUT FOR DEMO SAFETY) ----
# creds_info = st.secrets["GCP_SERVICE_ACCOUNT_JSON"]
# credentials = Credentials.from_service_account_info(creds_info, scopes=Scopes)
# gc = gspread.authorize(credentials)

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
    "invested in", "investing in", "portfolio", "capital",
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

    score = BASE_SCORE
    breakdown = [f"Base score from query (+{BASE_SCORE})"]
    signal_groups = set()

    if any(k in query for k in uae_keywords):
        score += 0.3
        breakdown.append("UAE mentioned in query (+0.3)")

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

# ---------------- SECOND PASS LOGIC ----------------

def extract_anchors(text):
    anchors = set()
    for kw in identity_keywords + behavior_keywords:
        if kw in text.lower():
            anchors.add(kw)
    company_matches = re.findall(r"at ([A-Z][A-Za-z0-9 &]+)", text)
    for c in company_matches:
        anchors.add(c.lower())
    return list(anchors)

def name_collision_risk(name):
    parts = name.split()
    if len(parts) < 2:
        return "high"
    if len(parts[1]) <= 2:
        return "high"
    return "low"

def build_second_pass_queries(name, anchors, collision):
    base = name
    queries = []
    if collision == "high":
        for a in anchors[:2]:
            queries.append(f"{base} {a}")
    else:
        queries.append(f"{base} united arab emirates")
        if anchors:
            queries.append(f"{base} {anchors[0]}")
    return queries[:2]

def score_second_pass(text, anchors):
    text = text.lower()
    score = 0
    signals = []

    for a in anchors:
        if a in text:
            score += 0.5
            signals.append(f"Anchor match: {a}")

    if any(k in text for k in identity_keywords):
        score += 1.5
        signals.append("Confirmed investor identity")

    if any(k in text for k in uae_keywords):
        score += 1.0
        signals.append("Confirmed UAE presence")

    if any(x in text for x in ["instagram", "twitter", "tiktok", "facebook"]):
        score += 0.3
        signals.append("External social presence")

    return min(score, 5.0), signals

# ---------------- UI ----------------

st.subheader("Live Discovery (First Pass)")

queries = [
    '"angel investor" UAE site:linkedin.com/in',
    'angel investor "UAE" site:linkedin.com/in'
]

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
                if norm_url in {normalize_url(x["URL"]) for x in st.session_state.results}:
                    continue

                combined = f"{title} {snippet}"
                score, conf, breakdown = score_text(combined, query, url)

                st.session_state.results.append({
                    "Name": title.split("-")[0].strip(),
                    "Title": title,
                    "Snippet": snippet,
                    "URL": url,
                    "Score": score,
                    "Confidence": conf,
                    "Signals": " | ".join(breakdown)
                })

df_first = pd.DataFrame(st.session_state.results)
st.subheader("First Pass Results")
st.dataframe(df_first, use_container_width=True)

st.subheader("Second Pass Verification")

if st.button("Run Second Pass"):
    with DDGS(timeout=10) as ddgs:
        for _, row in df_first.iterrows():
            name = row["Name"]
            anchors = extract_anchors(row["Snippet"])
            collision = name_collision_risk(name)
            queries_2 = build_second_pass_queries(name, anchors, collision)

            for q in queries_2:
                for r in ddgs.text(q, max_results=3, backend="html"):
                    text = f"{r.get('title','')} {r.get('body','')}"
                    score2, signals2 = score_second_pass(text, anchors)
                    if score2 > 0:
                        st.session_state.second_pass_results.append({
                            "Name": name,
                            "Query Used": q,
                            "Second Pass Score": score2,
                            "Signals": " | ".join(signals2),
                            "Source URL": r.get("href","")
                        })

df_second = pd.DataFrame(st.session_state.second_pass_results)
st.dataframe(df_second, use_container_width=True)
