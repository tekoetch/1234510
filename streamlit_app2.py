import streamlit as st
from ddgs import DDGS
import pandas as pd
import re

if "results" not in st.session_state:
    st.session_state.results = []

if "second_pass_results" not in st.session_state:
    st.session_state.second_pass_results = []

if "third_pass_results" not in st.session_state:
    st.session_state.third_pass_results = []

st.set_page_config(page_title="Leads Dashboard + Scoring Playground", layout="wide")
st.title("Leads Discovery + Scoring Playground")

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
    "seed", "pre-seed", "early-stage", "funding"
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

bonus_domains = ["theorg.com", "rocketreach.co"]

QUERY_BLOCKLIST = {"partner", "ceo", "co-founder"}

def normalize_url(url):
    return url.split("?")[0].lower().strip()

def score_text(text, query, url=""):
    text = text.lower()
    query = query.lower()
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

    if "Geography" in signal_groups:
        score += GEO_GROUP_BONUS
        breakdown.append(f"Geography group bonus (+{GEO_GROUP_BONUS})")

    score = min(score, 10.0)
    group_count = len(signal_groups)
    confidence = "High" if group_count >= 3 else "Medium" if group_count == 2 else "Low"
    breakdown.insert(0, f"Signal groups fired: {group_count}")
    return score, confidence, breakdown

def extract_anchors(text):
    anchors = {"identity": [], "behavior": [], "company": []}
    t = text.lower()

    for kw in identity_keywords:
        if kw in t and kw not in QUERY_BLOCKLIST:
            anchors["identity"].append(kw)

    for kw in behavior_keywords:
        if kw in t:
            anchors["behavior"].append(kw)

    companies = re.findall(r"at ([A-Z][A-Za-z0-9 &]+)", text)
    for c in companies:
        anchors["company"].append(c.strip())

    return anchors

def build_second_pass_queries(name, anchors):
    quoted_name = f'"{name}"'
    queries = []

    if anchors["identity"]:
        queries.append(f'{quoted_name} {anchors["identity"][0]}')
    elif anchors["behavior"]:
        queries.append(f'{quoted_name} {anchors["behavior"][0]}')
    elif anchors["company"]:
        queries.append(f'{quoted_name} {anchors["company"][0]} investor')

    queries.append(f'{quoted_name} "United Arab Emirates"')
    return queries[:2]


def score_second_pass(text, url, state):
    t = text.lower()
    score = 0
    breakdown = []

    if any(d in url for d in noise_domains):
        return 0, ["Noise domain"], False
    
    if "linkedin.com/pub/dir" in url:
        return 0, ["LinkedIn directory page ignored"], False

    if "/in/" in url:
        if state["linkedin_seen"]:
            return 0, ["Extra LinkedIn profile ignored"], False
        state["linkedin_seen"] = True

    if any(k in t for k in identity_keywords):
        if not state["identity_confirmed"]:
            score += 1.5
            breakdown.append("Confirmed investor identity")
            state["identity_confirmed"] = True

    if any(k in t for k in behavior_keywords):
        score += 0.5
        breakdown.append("Investment behavior language")

    if any(k in t for k in uae_keywords + mena_keywords):
        if state["geo_hits"] < 2 and state["identity_confirmed"]:
            score += 0.3
            breakdown.append("Supporting geography signal")
            state["geo_hits"] += 1

    for d in bonus_domains:
        if d in url and d not in state["domain_hits"]:
            score += 0.4
            breakdown.append(f"External confirmation via {d}")
            breakdown.append("Public contact information likely available")
            state["domain_hits"].add(d)

    return min(score, 5.0), breakdown, state["identity_confirmed"]

st.subheader("Discovery & Initial Scoring")

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
st.dataframe(df_first, use_container_width=True)

st.subheader("Identity Verification")

second_pass_placeholder = st.empty()

if st.button("Run Second Pass"):
    eligible_rows = df_first[df_first["Score"] >= 4.0]
    total_names = len(eligible_rows)

    progress = st.progress(0)
    status = st.empty()

    with DDGS(timeout=10) as ddgs:
        for i, (_, row) in enumerate(eligible_rows.iterrows(), start=1):
            status.write(f"Verifying identity for {row['Name']} ({i}/{total_names})")
            progress.progress(i / total_names)

            if row["Score"] < 4.0: continue

            name = row["Name"]
            anchors = extract_anchors(row["Snippet"])
            queries_2 = build_second_pass_queries(name, anchors)

            state = {
                "linkedin_seen": False,
                "geo_hits": 0,
                "identity_confirmed": False,
                "domain_hits": set()
            }

            partial_alignment = False

            for idx, q in enumerate(queries_2):
                if idx == 1 and not partial_alignment:
                    break

                try:
                    results = ddgs.text(q, max_results=20, backend="html")
                except Exception:
                    continue

                for r in results:
                    text = f"{r.get('title','')} {r.get('body','')}"
                    url = r.get("href", "")
                    score2, breakdown2, identity_seen = score_second_pass(text, url, state)

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

                        df_live = pd.DataFrame(st.session_state.second_pass_results)
                        second_pass_placeholder.dataframe(df_live, use_container_width=True)

df_second = pd.DataFrame(st.session_state.second_pass_results)
st.dataframe(df_second, use_container_width=True)

if not df_second.empty:
    consolidated = []
    for name, g in df_second.groupby("Name"):
        total_raw = g["Second Pass Score"].sum()
        total = min(total_raw, 6.0) 
        investor = "Yes" if any("Confirmed investor identity" in x for x in g["Score Breakdown"]) else "No"
        uae = "Yes" if any("UAE/MENA geography tied" in x for x in g["Score Breakdown"]) else "No"
        
        companies = set()
        has_rocketreach = False

        snippets = df_second[df_second["Name"] == name]["Snippet"].tolist()
        urls = df_second[df_second["Name"] == name]["Source URL"].tolist()

        for s in snippets:
            matches = re.findall(r"\b(at|with)\s+([A-Z][A-Za-z0-9 &]{3,})", s)
            for _, company in matches:
                companies.add(company.strip())

        for u in urls:
            if "rocketreach.co" in u:
                has_rocketreach = True

        company_str = ", ".join(sorted(companies)) if companies else ""
        enriched_social = "Yes (RocketReach)" if has_rocketreach else ""
        
        if investor == "Yes" and uae == "Yes" and total >= 4.5:
            verdict = "ACCEPT"
        elif total >= 2.5:
            verdict = "GOOD"
        else:
            verdict = "REJECT"
        
        consolidated.append({
            "Name": name,
            "First Pass Score": df_first[df_first["Name"] == name]["Score"].max(),
            "Second Pass Total": round(total, 1),
            "Evidence Rows": len(g),
            "Investor Confirmed": investor,
            "UAE Confirmed": uae,
            "Enriched Company": company_str,
            "Enriched Social": enriched_social,
            "Final Verdict": verdict
        })
    
    df_consolidated = pd.DataFrame(consolidated)
    st.subheader("Consolidated Review Table")
    st.dataframe(df_consolidated[df_consolidated["Final Verdict"].isin(["ACCEPT", "GOOD"])], use_container_width=True)
    st.metric(
        "Green List",
        len(df_consolidated[df_consolidated["Final Verdict"].isin(["ACCEPT", "GOOD"])])
    )
    st.metric(
    "Leads Verified",
    df_second["Name"].nunique()
    )

    
    for _, row in df_consolidated.iterrows():
        with st.expander(f"{row['Name']} (Verdict: {row['Final Verdict']})"):
            st.write("First-Pass Snippet:", df_first[df_first["Name"] == row["Name"]]["Snippet"].values[0])
            st.write("Verification Evidence:", df_second[df_second["Name"] == row["Name"]]["Score Breakdown"].tolist())

    st.subheader("Presence & Contact Enrichment")

    if st.button("Run Third Pass Enrichment"):
        with DDGS(timeout=10) as ddgs:
            eligible = df_consolidated[df_consolidated["Final Verdict"] != "REJECT"]["Name"].tolist()

            for name in eligible:
                queries_3 = [
                    f'site:instagram.com "{name}"',
                    f'site:x.com "{name}"',
                    f'site:facebook.com "{name}"',
                    f'"{name}" email',
                    f'"{name}" phone'
                ]

                for q in queries_3:
                    for r in ddgs.text(q, max_results=2, backend="html"):
                        st.session_state.third_pass_results.append({
                            "Name": name,
                            "Query Used": q,
                            "Snippet": f"{r.get('title','')} {r.get('body','')}",
                            "Source URL": r.get("href","")
                        })

    df_third = pd.DataFrame(st.session_state.third_pass_results)
    st.dataframe(df_third, use_container_width=True)
