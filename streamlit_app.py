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

st.markdown("""
### System Overview
This demo discovers potential UAE angel investors/family offices via public searches:
- **First Pass**: Broad discovery from LinkedIn-like sources.
- **Second Pass**: Verifies identity with targeted queries using first-pass context (e.g., append 'Dubai angel investor' if mentioned), enriches with companies/social URLs, and discards if no UAE/investment ties.
- **Third Pass (Optional)**: Enriches verified leads with dynamic queries (e.g., 'Name Dubai angel investor email').
Leads are scored on signals like geography (UAE/MENA) and behaviors ('invested in'); verdicts require evidence for defensibility.
""")

freeze_scoring = st.toggle("Freeze scoring (manual review mode)", value=False, help="Lock scores for manual tweaks during demo.")

st.sidebar.header("Scoring Controls")
BASE_SCORE = st.sidebar.slider("Base score (query baseline)", 0.0, 3.0, 1.5, 0.1, help="Baseline score for all results")
IDENTITY_WEIGHT = st.sidebar.slider("Primary identity boost", 0.5, 3.0, 1.8, 0.1, help="Boost for primary investor keywords")
IDENTITY_DIMINISHING_WEIGHT = st.sidebar.slider("Additional identity boost", 0.2, 1.5, 0.8, 0.1, help="Diminishing boost for extra identities")
BEHAVIOR_WEIGHT = st.sidebar.slider("Behavior keyword boost", 0.1, 2.0, 0.4, 0.1, help="Boost for investment behavior keywords")
BEHAVIOR_GROUP_BONUS = st.sidebar.slider("Identity + behavior synergy bonus", 0.0, 1.0, 0.5, 0.1, help="Bonus for combined identity and behavior")
SENIORITY_WEIGHT = st.sidebar.slider("Seniority keyword boost", 0.2, 3.0, 1.0, 0.1, help="Boost for seniority terms")
SENIORITY_GROUP_BONUS = st.sidebar.slider("Seniority group bonus", 0.0, 1.0, 0.5, 0.1, help="Bonus for multiple seniority")
GEO_GROUP_BONUS = st.sidebar.slider("Geography group bonus", 0.0, 1.0, 0.5, 0.1, help="Bonus for UAE/MENA geography")

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
    anchors = {"identity": [], "behavior": [], "geo": [], "company": []}
    t = text.lower()
    for kw in identity_keywords:
        if kw in t and kw not in QUERY_BLOCKLIST:
            anchors["identity"].append(kw)
    for kw in behavior_keywords:
        if kw in t:
            anchors["behavior"].append(kw)
    for kw in uae_keywords + mena_keywords:
        if kw in t:
            anchors["geo"].append(kw)
    companies = re.findall(r"(at|@|with|of|for|in|to|from|at the|of the|for the|in the|to the|from the) ([A-Z][A-Za-z0-9 &']+)", t, re.I)
    for _, c in companies:
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
    return list(set(queries[:2]))

def score_second_pass(text, url, state, first_snippet):
    t = text.lower()
    score = 0
    breakdown = []
    if any(d in url for d in noise_domains):
        return 0, ["Noise domain"], False
    if "linkedin.com/pub/dir" in url:
        return 0, ["LinkedIn directory ignored"], False
    if "/in/" in url:
        if state["linkedin_seen"]:
            return 0, ["Extra LinkedIn ignored"], False
        state["linkedin_seen"] = True
    first_kw = set(re.findall(r'\b\w+\b', first_snippet.lower()))
    second_kw = set(re.findall(r'\b\w+\b', t))
    overlap = len(first_kw & second_kw) / len(first_kw) if first_kw else 0
    if overlap > 0.3:
        score += 1.0
        breakdown.append(f"Snippet overlap ({overlap:.2f}) confirms relevance")
    identity_hits = [k for k in identity_keywords if k in t]
    if identity_hits:
        score += 1.5
        breakdown.append("Confirmed investor identity")
        state["identity_confirmed"] = True
        for k in identity_hits[1:]:
            score += 0.5
            breakdown.append(f"Additional identity '{k}'")
    behavior_hits = [k for k in behavior_keywords if k in t]
    if behavior_hits:
        score += 0.5
        breakdown.append("Investment behavior confirmed")
        for k in behavior_hits[1:]:
            score += 0.2
            breakdown.append(f"Additional behavior '{k}'")
    geo_hits = [k for k in uae_keywords + mena_keywords if k in t]
    if geo_hits:
        score += 0.3
        breakdown.append("UAE/MENA geography tied")
        state["geo_hits"] += 1
        for k in geo_hits[1:]:
            score += 0.1
            breakdown.append(f"Additional geo '{k}'")
    for d in bonus_domains:
        if d in url:
            score += 0.4
            breakdown.append(f"Potential contact via {d}")
    company = re.findall(r"(at|@|with|of|for|in|to|from|at the|of the|for the|in the|to the|from the) ([A-Z][A-Za-z0-9 &']+)", t, re.I)
    companies_str = ", ".join(set(c[1].strip() for c in company)) if company else ""
    if companies_str:
        breakdown.append(f"Enriched company: {companies_str}")
        score += 0.4
    if not (state["geo_hits"] > 0 and (state["identity_confirmed"] or len(behavior_hits) > 0)):
        breakdown.append("Discard: No UAE/investment tie")
        score = 0
    return min(score, 5.0), breakdown, state["identity_confirmed"]

st.subheader("Discovery & Initial Scoring")
custom_queries = st.text_area("Custom Queries (one per line)", value='\n'.join([
    '"angel investor" UAE site:linkedin.com/in',
    'angel investor "UAE" site:linkedin.com/in'
]))
queries = [q.strip() for q in custom_queries.split("\n") if q.strip()]

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
if st.button("Run Second Pass"):
    with DDGS(timeout=10) as ddgs:
        for _, row in df_first.iterrows():
            if row["Score"] < 4.0:
                continue
            name = row["Name"]
            first_snippet = row["Snippet"]
            anchors = extract_anchors(first_snippet)
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
                    score2, breakdown2, identity_seen = score_second_pass(text, url, state, first_snippet)
                    if score2 > 0 and "Discard" not in " | ".join(breakdown2):
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
st.dataframe(df_second, use_container_width=True)

if not df_second.empty:
    consolidated = []
    for name, g in df_second.groupby("Name"):
        total = g["Second Pass Score"].sum()
        investor = "Yes" if any("Confirmed investor identity" in x for x in g["Score Breakdown"]) else "No"
        uae = "Yes" if any("UAE/MENA geography tied" in x for x in g["Score Breakdown"]) else "No"
        companies = set()
        has_rocketreach = False
        for b in g["Score Breakdown"]:
            b_lower = b.lower()
            if "enriched company" in b_lower:
                try:
                    companies.add(b.split(": ", 1)[1].strip())
                except:
                    pass
            if "potential contact via rocketreach" in b_lower:
                has_rocketreach = True
        company_str = ", ".join(companies) if companies else ""
        enriched_social = "Yes (RocketReach)" if has_rocketreach else ""
        verdict = "ACCEPT" if total >= 5 and investor == "Yes" else "GOOD" if total >= 2 else "REJECT"
        consolidated.append({
            "Name": name,
            "First Pass Score": df_first[df_first["Name"] == name]["Score"].max(),
            "Second Pass Total": round(total, 2),
            "Evidence Rows": len(g),
            "Investor Confirmed": investor,
            "UAE Confirmed": uae,
            "Enriched Company": company_str,
            "Enriched Social": enriched_social,
            "Final Verdict": verdict
        })
    df_consolidated = pd.DataFrame(consolidated)
    st.subheader("Consolidated Review Table")
    st.dataframe(df_consolidated, use_container_width=True)
    st.metric("Accepted Leads", len(df_consolidated[df_consolidated["Final Verdict"] == "ACCEPT"]))
    for _, row in df_consolidated.iterrows():
        with st.expander(f"{row['Name']} (Verdict: {row['Final Verdict']})"):
            st.write("First-Pass Snippet:", df_first[df_first["Name"] == row["Name"]]["Snippet"].values[0])
            st.write("Verification Evidence:", df_second[df_second["Name"] == row["Name"]]["Score Breakdown"].tolist())

st.subheader("Presence & Contact Enrichment")
run_third = st.checkbox("Run Third Pass", value=False)
if run_third and st.button("Run Third Pass Enrichment"):
    with DDGS(timeout=10) as ddgs:
        eligible = df_consolidated[df_consolidated["Final Verdict"] != "REJECT"]["Name"].tolist()
        for name in eligible:
            row = df_consolidated[df_consolidated["Name"] == name].iloc[0]
            geo = "Dubai UAE MENA" if row["UAE Confirmed"] == "Yes" else ""
            investor_kw = "angel investor invested in" if row["Investor Confirmed"] == "Yes" else ""
            context = f"{geo} {investor_kw}".strip()
            queries_3 = [
                f'site:instagram.com "{name}" {context}',
                f'site:x.com "{name}" {context}',
                f'site:facebook.com "{name}" {context}',
                f'"{name}" {context} email',
                f'"{name}" {context} phone'
            ]
            for q in queries_3:
                for r in ddgs.text(q, max_results=2, backend="html"):
                    snippet = f"{r.get('title','')} {r.get('body','')}"
                    email = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", snippet)
                    phone = re.search(r"\+\d{1,3}[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}", snippet)
                    st.session_state.third_pass_results.append({
                        "Name": name,
                        "Query Used": q,
                        "Snippet": snippet,
                        "Email": email.group(0) if email else "None",
                        "Phone": phone.group(0) if phone else "None",
                        "Source URL": r.get("href","")
                    })
    df_third = pd.DataFrame(st.session_state.third_pass_results)
    st.dataframe(df_third, use_container_width=True)
    for _, row in df_third.iterrows():
        if row["Email"] == "None" and row["Phone"] == "None":
            df_consolidated.loc[df_consolidated["Name"] == row["Name"], "Final Verdict"] = "Discard/Not Accurate"
