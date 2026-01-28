import streamlit as st
from ddgs import DDGS
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timezone
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Lead Discovery", layout="wide")
st.title("Lead Discovery")

conn = st.connection("gsheets", type=GSheetsConnection)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_info = st.secrets["GCP_SERVICE_ACCOUNT_JSON"]
credentials = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
gc = gspread.authorize(credentials)

display_col = {
    "result_id": "Result ID",
    "query_used": "Query Used",
    "title": "Title",
    "snippet": "Snippet",
    "url": "URL",
    "first_seen": "First Seen",
    "last_checked": "Last Checked",
    "score": "Score",
    "confidence_level": "Confidence",
    "matched_keywords": "Matched Keywords",
    "signal_breakdown": "Why It Scored This Way",
}

internal_col = list(display_col.keys())

try:
    existing_df = conn.read(worksheet="Sheet1")
    existing_df.columns = (
        existing_df.columns
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
    )
    existing_df = existing_df.reindex(columns=internal_col)
except Exception:
    existing_df = pd.DataFrame(columns=internal_col)

identity_keywords = [
    "angel investor",
    "angel investing",
    "family office",
    "venture investor",
    "private investor"
]

behavior_keywords = [
    "invested in",
    "portfolio",
    "funding",
    "seed",
    "pre-seed",
    "early-stage"
]

seniority_keywords = [
    "founder",
    "co-founder",
    "partner",
    "chairman",
    "managing director",
    "principal"
]

uae_keywords = ["uae", "dubai", "abu dhabi", "emirates"]
mena_keywords = ["uae", "dubai", "abu dhabi", "emirates", "middle east", "mena"]

def score_result(text):
    text = text.lower()

    score = 1
    signal_breakdown = []
    matched_keywords = []

    # Hard geographic gate
    if not any(k in text for k in mena_keywords):
        return {
            "score": 1,
            "confidence": "Low",
            "matched_keywords": [],
            "signal_breakdown": ["No MENA relevance"]
        }

    signal_breakdown.append("MENA relevance")

    if any(k in text for k in uae_keywords):
        score += 3
        signal_breakdown.append("UAE presence")
        matched_keywords += uae_keywords

    if any(k in text for k in identity_keywords):
        score += 3
        signal_breakdown.append("Investor identity signal")
        matched_keywords += identity_keywords

    if any(k in text for k in behavior_keywords):
        score += 2
        signal_breakdown.append("Investment activity signal")
        matched_keywords += behavior_keywords

    if any(k in text for k in seniority_keywords):
        score += 2
        signal_breakdown.append("Senior role/title")
        matched_keywords += seniority_keywords

    score = min(score, 10)

    if score >= 8:
        confidence = "High"
    elif score >= 5:
        confidence = "Medium"
    else:
        confidence = "Low"

    return {
        "score": score,
        "confidence": confidence,
        "matched_keywords": sorted(set([k for k in matched_keywords if k in text])),
        "signal_breakdown": signal_breakdown
    }

queries = [
    '"angel investor" UAE site:linkedin.com/in',
    '"family office" Dubai site:linkedin.com/in'
]

results = []

if st.button("Run Discovery"):
    with DDGS(timeout=10) as ddgs:
        for query in queries:
            st.write(f"Running query: {query}")
            for r in ddgs.text(query, max_results=5, backend="html"):
                title = r.get("title", "")
                snippet = r.get("body", "")
                url = r.get("href", "")
                combined_text = f"{title} {snippet}"

                scoring = score_result(combined_text)

                now = datetime.now(timezone.utc).isoformat()
                result_id = url.lower().strip()

                results.append({
                    "result_id": result_id,
                    "query_used": query,
                    "title": title,
                    "snippet": snippet,
                    "url": url,
                    "first_seen": now,
                    "last_checked": now,
                    "score": scoring["score"],
                    "confidence_level": scoring["confidence"],
                    "matched_keywords": ", ".join(scoring["matched_keywords"]),
                    "signal_breakdown": " | ".join(scoring["signal_breakdown"])
                })

new_df = pd.DataFrame(results).reindex(columns=internal_col)

if not new_df.empty:
    combined_df = pd.concat([existing_df, new_df])
    combined_df = combined_df.drop_duplicates(subset="result_id", keep="first")

    display_df = combined_df.rename(columns=display_col)

    sheet_url = "YOUR_SHEET_URL_HERE"
    sh = gc.open_by_url(sheet_url)
    ws = sh.worksheet("Sheet1")

    ws.clear()
    ws.update([display_df.columns.tolist()] + display_df.values.tolist())

    st.success(f"{len(new_df)} new leads added. Total: {len(combined_df)}")
else:
    st.info("No new results found.")

if "combined_df" in locals() and not combined_df.empty:
    st.dataframe(combined_df.sort_values("first_seen", ascending=False), use_container_width=True)
