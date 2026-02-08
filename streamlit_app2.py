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
    "seed", "pre-seed", "early-stage", "funding",
    "venture capital", "private equity", "real estate",
    "fundraising", "investment portfolio", "wealth funds"
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

def is_duplicate_url(url, existing_results, title, snippet):
    norm = normalize_url(url)
    for r in existing_results:
        if normalize_url(r.get("URL", "")) == norm:
            old_text = (r.get("Title","") + r.get("Snippet","")).lower()
            new_text = (title + snippet).lower()
            if len(set(new_text.split()) - set(old_text.split())) < 5:
                return True
    return False


def normalize_url(url):
    return url.split("?")[0].lower().strip()

def soft_truncate_ellipsis(text: str) -> str:
    if not text:
        return text
    if "..." in text:
        return text.split("...")[0].strip()
    return text


def score_text(text, query, url=""):
    breakdown = []
    signal_groups = set()

    text = text.lower()
    score = BASE_SCORE

    location_match = re.search(r"location:\s*([^\n|·]+)", text, re.IGNORECASE)
    if location_match:
        loc = location_match.group(1).lower()
        if any(k in loc for k in uae_keywords + mena_keywords):
            score += 0.5
            breakdown.append("Explicit UAE location (+0.5)")
        elif any(bad in loc for bad in ["london", "singapore", "new york", "usa", "uk", "india"]):
            score -= 1.5 
            breakdown.append("Non-MENA location detected (-1.5)")

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

    if "ae.linkedin.com/in" in url:
        score += GEO_GROUP_BONUS
        breakdown.append("UAE LinkedIn domain")    

    score = min(score, 10.0)
    confidence = "High" if len(signal_groups) >= 3 else "Medium" if len(signal_groups) == 2 else "Low"
    breakdown.insert(0, f"Signal groups fired: {len(signal_groups)}")

    return score, confidence, breakdown

def is_valid_person_name(name):
    if not name:
        return False
    if len(name.split()) < 2:
        return True
    if name.lower() in {"angel investor", "venture capital"}:
        return False
    return True


def extract_name(title):
    for sep in [" - ", " | ", " – ", " — "]:
        if sep in title:
            candidate = title.split(sep)[0].strip()
            return candidate
    return title.strip()


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
                raw_title = r.get("title", "")
                raw_snippet = r.get("body", "")

                title = soft_truncate_ellipsis(raw_title)
                snippet = soft_truncate_ellipsis(raw_snippet)

                url = r.get("href", "")

                if not url:
                    continue

                if any(bad in normalize_url(url) for bad in blocked_urls):
                    continue

                combined = f"{title} {snippet}"
                score, conf, breakdown = score_text(combined, query, url)
                name = extract_name(title)

                if not is_valid_person_name(name):
                    continue

                if is_duplicate_url(url, st.session_state.results, title, snippet):
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
    df_first[["Reviewed", "Name", "Title", "Snippet", "Score", "Confidence", "Signals", "URL"]],
    use_container_width=True
)

st.subheader("Checklist Helper")

if df_first.empty:
    st.info("No rows available yet.")
else:
    selected_index = st.number_input(
        "Row number to copy (0-based index)",
        min_value=0,
        max_value=len(df_first) - 1,
        value=0,
        step=1
    )

    row = df_first.iloc[selected_index]

    checklist_text = f"""
-----------------------------------------------
RAW TITLE TEXT (VERBATIM):
{row.get('Title', '')}

RAW SNIPPET TEXT (VERBATIM):
{row.get('Snippet', '')}

SEARCH MODE (QUOTED / UNQUOTED):

QUERY USED:
(manual)

NAME COMMONALITY (RARE / MODERATE / VERY COMMON, multiple linkedin profile with similar name, chance of false positive in second pass):

FINAL SCORE:
{row.get('Score', '')}

SYSTEM CONFIDENCE (LOW / MEDIUM / HIGH, should they move on to second pass?):
{row.get('Confidence', '')}

TOP CONTRIBUTORS (exact keywords or signals that boosted score):
{row.get('Signals', '')}

YOUR VERDICT (REJECT / SECOND PASS OK / CLEARLY GOOD):

SNIPPET ALONE FELT SUFFICIENT TO DECIDE? (YES / NO):

IF SCORE WERE 0.2 LOWER, WOULD YOU STILL KEEP IT? (YES / NO):

DID YOU FEEL THE NEED TO CLICK A PROFILE? (YES / NO):

IF YES, WHY? (ambiguity / role unclear / geography unclear / seniority unclear / other):

FALSE-POSITIVE RISK (LOW / MEDIUM / HIGH):

MISSING-BUT-OBVIOUS SIGNAL (OPTIONAL):

EDGE-CASE TYPE (if any):
(common name / inflated title / geography mismatch / keyword bait / unclear investor type / other):

NOTES (OPTIONAL, is role explicit and suggest influence capital or decision authority, any signals here the person invests or allocates capital or advises on investments, anything unique that stands out):
"""

    st.text_area(
        "Copy into your checklist",
        checklist_text,
        height=500
    )
