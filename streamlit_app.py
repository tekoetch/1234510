import streamlit as st
from ddgs import DDGS
import pandas as pd
import re

# Session state setup (unchanged)
if "results" not in st.session_state:
    st.session_state.results = []
if "second_pass_results" not in st.session_state:
    st.session_state.second_pass_results = []
if "third_pass_results" not in st.session_state:
    st.session_state.third_pass_results = []

st.set_page_config(page_title="Leads Dashboard + Scoring Playground", layout="wide")
st.title("UAE Investor Leads Discovery & Scoring Demo")

# System Overview for Demo
st.markdown("""
### System Overview
This demo discovers potential UAE angel investors/family offices via public searches:
- **First Pass**: Broad discovery from LinkedIn-like sources.
- **Second Pass**: Verifies identity with targeted queries using first-pass context (e.g., append 'Dubai angel investor' if mentioned), enriches with companies/social URLs, and discards if no UAE/investment ties.
- **Third Pass (Optional)**: Enriches verified leads with dynamic queries (e.g., 'Name Dubai angel investor email').
Leads are scored on signals like geography (UAE/MENA) and behaviors ('invested in'); verdicts require evidence for defensibility.
""")

# Scoring controls (unchanged, but add tooltips)
freeze_scoring = st.toggle("Freeze scoring (manual review mode)", value=False, help="Lock scores for manual tweaks during demo.")
st.sidebar.header("Scoring Controls")
# ... (all sliders unchanged, add help= "Explanation..." to each)

# Keyword lists (unchanged)
# ... 

# Utility functions with improvements
def normalize_url(url):
    return url.split("?")[0].lower().strip()

def score_text(text, query, url=""):  # Unchanged

def extract_anchors(text):  # Enhanced to pull geo too
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
    companies = re.findall(r"at ([A-Z][A-Za-z0-9 &]+)", text)
    for c in companies:
        anchors["company"].append(c.strip())
    return anchors

def build_second_pass_queries(name, anchors, first_snippet):
    quoted_name = f'"{name}"'
    queries = []
    # Append first-pass context: Top keywords from snippet
    snippet_keywords = re.findall(r'\b(angel investor|family office|invested in|dubai|uae|mena)\b', first_snippet.lower())
    context_str = " ".join(set(snippet_keywords))  # Unique for precision
    base_query = f'{quoted_name} {context_str}' if context_str else quoted_name
    if anchors["identity"]:
        queries.append(f'{base_query} {anchors["identity"][0]}')
    elif anchors["behavior"]:
        queries.append(f'{base_query} {anchors["behavior"][0]}')
    elif anchors["company"]:
        queries.append(f'{base_query} {anchors["company"][0]} investor')
    if anchors["geo"]:
        queries.append(f'{base_query} {anchors["geo"][0]} investor')
    queries.append(f'{base_query} "United Arab Emirates"')
    return list(set(queries[:3]))  # Up to 3 unique for depth

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
    # Corroborate with first_snippet: Check overlap in keywords
    first_kw = set(re.findall(r'\b\w+\b', first_snippet.lower()))
    second_kw = set(re.findall(r'\b\w+\b', t))
    overlap = len(first_kw & second_kw) / len(first_kw) if first_kw else 0
    if overlap > 0.3:  # Threshold for relevance
        score += 1.0
        breakdown.append(f"Snippet overlap ({overlap:.2f}) confirms relevance")
    # Verification logic (enhanced for UAE/investment ties)
    identity_seen = any(k in t for k in identity_keywords)
    behavior_seen = any(k in t for k in behavior_keywords)
    geo_seen = any(k in t for k in uae_keywords + mena_keywords)
    if identity_seen and not state["identity_confirmed"]:
        score += 1.5
        breakdown.append("Confirmed investor identity")
        state["identity_confirmed"] = True
    if behavior_seen:
        score += 0.5
        breakdown.append("Investment behavior confirmed")
    if geo_seen and state["identity_confirmed"]:
        score += 0.3 * state["geo_hits"]  # Cumulative
        breakdown.append("UAE/MENA geography tied")
        state["geo_hits"] += 1
    # Enrichment: Parse company/social
    company = re.findall(r"at ([A-Z][A-Za-z0-9 &]+)", t)
    social_urls = re.findall(r'(linkedin\.com/in/[\w-]+|x\.com/[\w-]+)', t)
    if company:
        breakdown.append(f"Enriched company: {company[0]}")
        score += 0.4
    if social_urls:
        breakdown.append(f"Enriched social: {social_urls[0]}")
        score += 0.4
    # Discard if weak
    if not (geo_seen and (identity_seen or behavior_seen)):
        breakdown.append("Discard: No UAE/investment tie")
        score = 0
    return min(score, 5.0), breakdown, state["identity_confirmed"]

# Discovery Pass (add custom queries)
st.subheader("Discovery & Initial Scoring")
custom_queries = st.text_area("Custom Queries (one per line)", value="\n".join(queries))
queries = [q.strip() for q in custom_queries.split("\n") if q.strip()]
if st.button("Run Discovery"):
    # ... (unchanged loop, but add st.spinner("Discovering..."))

# Verification Pass (updated with new functions)
st.subheader("Identity Verification & Enrichment")
if st.button("Run Second Pass"):
    with st.spinner("Verifying..."):
        for _, row in df_first.iterrows():
            if row["Score"] < 4.0:
                continue
            name = row["Name"]
            first_snippet = row["Snippet"]
            anchors = extract_anchors(first_snippet)
            queries_2 = build_second_pass_queries(name, anchors, first_snippet)
            state = {"linkedin_seen": False, "geo_hits": 0, "identity_confirmed": False, "domain_hits": set()}
            partial_alignment = False
            for idx, q in enumerate(queries_2):
                if idx > 0 and not partial_alignment:
                    break
                try:
                    results = ddgs.text(q, max_results=20)
                except:
                    continue
                for r in results:
                    text = f"{r.get('title','')} {r.get('body','')}"
                    url = r.get("href", "")
                    score2, breakdown2, identity_seen = score_second_pass(text, url, state, first_snippet)
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

# Consolidated (enhanced with enrichment columns)
if not df_second.empty:
    consolidated = []
    for name, g in df_second.groupby("Name"):
        total = g["Second Pass Score"].sum()
        investor = "Yes" if any("Confirmed investor" in x for x in g["Score Breakdown"]) else "No"
        uae = "Yes" if any("UAE/MENA" in x for x in g["Score Breakdown"]) else "No"
        company = next((b.split(": ")[1] for b in g["Score Breakdown"] if "Enriched company" in b), "None")
        social = next((b.split(": ")[1] for b in g["Score Breakdown"] if "Enriched social" in b), "None")
        if company == "None" and social == "None":
            verdict = "Discard/Not Accurate"
        else:
            verdict = "ACCEPT" if total >= 5 and investor == "Yes" else "GOOD" if total >= 2 else "REJECT"
        consolidated.append({
            "Name": name,
            "First Pass Score": df_first[df_first["Name"] == name]["Score"].max(),
            "Second Pass Total": round(total, 2),
            "Evidence Rows": len(g),
            "Investor Confirmed": investor,
            "UAE Confirmed": uae,
            "Enriched Company": company,
            "Enriched Social": social,
            "Final Verdict": verdict
        })
    df_consolidated = pd.DataFrame(consolidated)
    st.subheader("Consolidated Leads")
    st.dataframe(df_consolidated)
    # Metrics for demo
    st.metric("Accepted Leads", len(df_consolidated[df_consolidated["Final Verdict"] == "ACCEPT"]))
    # Expanders for explainability
    for _, row in df_consolidated.iterrows():
        with st.expander(f"{row['Name']} (Verdict: {row['Final Verdict']})"):
            st.write("First-Pass Snippet:", df_first[df_first["Name"] == row["Name"]]["Snippet"].values[0])
            st.write("Verification Evidence:", df_second[df_second["Name"] == row["Name"]]["Score Breakdown"].tolist())

# Optional Third Pass (dynamic, conditional)
st.subheader("Optional Enrichment (for Verified Leads)")
run_third = st.checkbox("Run Third Pass", value=False)
if run_third and st.button("Enrich Verified"):
    with st.spinner("Enriching..."):
        eligible = df_consolidated[df_consolidated["Final Verdict"].isin(["ACCEPT", "GOOD"])]["Name"].tolist()
        for name in eligible:
            # Dynamic: Use keywords from previous
            row = df_consolidated[df_consolidated["Name"] == name].iloc[0]
            geo = "Dubai UAE MENA" if row["UAE Confirmed"] == "Yes" else ""
            investor_kw = "angel investor invested in" if row["Investor Confirmed"] == "Yes" else ""
            context = f"{geo} {investor_kw}".strip()
            queries_3 = [
                f'"{name}" {context} site:instagram.com',
                f'"{name}" {context} site:x.com',
                f'"{name}" {context} site:facebook.com',
                f'"{name}" {context} email',
                f'"{name}" {context} phone'
            ]
            for q in queries_3:
                for r in ddgs.text(q, max_results=2):
                    snippet = f"{r.get('title','')} {r.get('body','')}"
                    # Parse for actual enrichment
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
    st.dataframe(df_third)
    # Update discards if no enrichment
    for _, row in df_third.iterrows():
        if row["Email"] == "None" and row["Phone"] == "None":
            df_consolidated.loc[df_consolidated["Name"] == row["Name"], "Final Verdict"] = "Discard/Not Accurate"
