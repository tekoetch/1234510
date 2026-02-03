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

noise_domains = [
    "wikipedia.org", "saatchiart.com", "researchgate.net",
    "academia.edu", "sciprofiles.com"
]

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

def extract_anchors(text):
    anchors = set()
    t = text.lower()
    for kw in identity_keywords + behavior_keywords + seniority_keywords:
        if kw in t:
            anchors.add(kw)
    companies = re.findall(r"at ([A-Z][A-Za-z0-9 &]+)", text)
    for c in companies:
        anchors.add(c.lower())
    return list(anchors)

def name_collision_risk(name):
    parts = name.split()
    if len(parts) < 2:
        return "high"
    if len(parts[0]) <= 3 and len(parts[1]) <= 3:
        return "high"
    return "low"

def build_second_pass_queries(name, anchors):
    queries = [f"{name} united arab emirates"]
    if anchors:
        queries.append(f"{name} {anchors[0]}")
    return queries

def score_second_pass(text, anchors, url):
    t = text.lower()
    score = 0
    breakdown = []

    if any(d in url for d in noise_domains):
        return 0, ["Noise domain"]

    anchor_hits = [a for a in anchors if a in t]
    for a in anchor_hits:
        score += 0.5
        breakdown.append(f"Anchor match: {a}")

    if any(k in t for k in identity_keywords):
        score += 1.5
        breakdown.append("Confirmed investor identity")

    if any(k in t for k in uae_keywords):
        score += 1.0
        breakdown.append("Confirmed UAE presence")

    if any(x in t for x in ["instagram", "twitter", "tiktok", "facebook"]):
        score += 0.3
        breakdown.append("External social presence")

    return min(score, 5.0), breakdown

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
            queries_2 = build_second_pass_queries(name, anchors)

            partial_alignment = False

            for idx, q in enumerate(queries_2):
                if idx == 1 and not partial_alignment:
                    break

                for r in ddgs.text(q, max_results=3, backend="html"):
                    text = f"{r.get('title','')} {r.get('body','')}"
                    url = r.get("href", "")
                    score2, breakdown2 = score_second_pass(text, anchors, url)
                    if score2 > 0:
                        partial_alignment = True
                        st.session_state.second_pass_results.append({
                            "Name": name,
                            "Query Used": q,
                            "Snippet": text,
                            "Second Pass Score": score2,
                            "Score Breakdown": " | ".join(breakdown2),
                            "Source URL": url
                        })

df_second = pd.DataFrame(st.session_state.second_pass_results)
st.subheader("Second Pass Evidence")
st.dataframe(df_second, use_container_width=True)

if not df_second.empty:
    consolidated = []
    for name, g in df_second.groupby("Name"):
        total = g["Second Pass Score"].sum()
        investor = "Yes" if any("Confirmed investor" in x for x in g["Score Breakdown"]) else "No"
        uae = "Yes" if any("Confirmed UAE" in x for x in g["Score Breakdown"]) else "No"
        verdict = "ACCEPT" if total >= 5 and investor == "Yes" else "REVIEW" if total >= 2 else "REJECT"
        consolidated.append({
            "Name": name,
            "First Pass Score": df_first[df_first["Name"] == name]["Score"].max(),
            "Second Pass Total": round(total, 2),
            "Evidence Rows": len(g),
            "Investor Confirmed": investor,
            "UAE Confirmed": uae,
            "Final Verdict": verdict
        })

    df_consolidated = pd.DataFrame(consolidated)
    st.subheader("Consolidated Review Table")
    st.dataframe(df_consolidated, use_container_width=True)
