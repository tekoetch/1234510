import streamlit as st
from ddgs import DDGS
import pandas as pd
import re
from first_pass import score_text

if "results" not in st.session_state:
    st.session_state.results = []

st.set_page_config(page_title="Leads Dashboard", layout="wide")
st.title("Leads Discovery")

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

def find_existing_person(url, existing_results):
    norm = normalize_url(url)
    for i, r in enumerate(existing_results):
        if normalize_url(r.get("URL", "")) == norm:
            return i
    return None

def is_valid_person_name(name):
    if not name:
        return False
    if len(name.split()) < 2:
        return False
    if re.fullmatch(r"[A-Z][a-z]+\s*\.", name):
        return False
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
    value=20,
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

                if is_duplicate_url(
                    url,
                    st.session_state.results,
                    title,
                    snippet
                ):
                    continue

                combined = f"{title} {snippet}"
                score, conf, breakdown, enriched_company = score_text(combined, query, url)
                name = extract_name(title)

                if not is_valid_person_name(name):
                    continue

                existing_idx = find_existing_person(url, st.session_state.results)

                if existing_idx is not None:
                    existing = st.session_state.results[existing_idx]

                    existing["Snippet"] += "\n---\n" + snippet
                    existing["Title"] = existing["Title"]
                    existing["Score"] = max(existing["Score"], score)

                    old_signals = set(existing["Signals"].split(" | "))
                    new_signals = set(breakdown)
                    existing["Signals"] = " | ".join(sorted(old_signals | new_signals))

                    if conf == "High":
                        existing["Confidence"] = "High"
                    elif conf == "Medium" and existing["Confidence"] == "Low":
                        existing["Confidence"] = "Medium"

                else:
                    st.session_state.results.append({
                        "Reviewed": False,
                        "Name": name,
                        "Title": title,
                        "Snippet": snippet,
                        "URL": url,
                        "Score": score,
                        "Confidence": conf,
                        "Signals": " | ".join(breakdown),
                        "Enriched Company": enriched_company
                    })

EXPECTED_COLUMNS = [
    "Reviewed", "Name", "Title", "Snippet",
    "URL", "Score", "Confidence", "Signals", "Enriched Company"
]

df_first = pd.DataFrame(st.session_state.results)

for col in EXPECTED_COLUMNS:
    if col not in df_first.columns:
        df_first[col] = []

st.dataframe(
    df_first[["Reviewed", "Name", "Title", "Snippet", "Enriched Company", "Score", "Confidence", "Signals", "URL"]],
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
