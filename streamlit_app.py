import streamlit as st
from ddgs import DDGS
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timezone
import gspread
from google.oauth2.service_account import Credentials
import os

st.set_page_config(page_title="Leads Dashboard", layout="wide")
st.title("Dashboard testing")

conn = st.connection("gsheets", type=GSheetsConnection)

Scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_info = st.secrets["GCP_SERVICE_ACCOUNT_JSON"]
credentials = Credentials.from_service_account_info(creds_info, scopes=Scopes)

gc = gspread.authorize(credentials)

display_col = {
    "result_id": "Result ID",
    "query_used": "Query Used",
    "title": "Title",
    "snippet": "Snippet",
    "url": "URL",
    "classification": "Classification",
    "first_seen": "First Seen",
    "last_checked": "Last Checked",
}

try:
    existing_df = conn.read(worksheet="Sheet1")
except Exception:
    existing_df = pd.DataFrame(columns=[
        "Result ID",
        "Query Used",
        "Title",
        "Snippet",
        "URL",
        "Classification",
        "First Seen",
        "Last Checked"
    ])

existing_df.columns = (
    existing_df.columns
    .str.strip()
    .str.lower()
    .str.replace(" ", "_")
)

internal_col = [
    "result_id",
    "query_used",
    "title",
    "snippet",
    "url",
    "first_seen",
    "last_checked",
    "score",
    "confidence_level",
    "matched_keywords",
    "signal_breakdown",
]

existing_df = existing_df.reindex(columns=internal_col)

group_a = ["angel investor", "angel investing", "family office",
           "private investor", "early-stage investor", "venture investor"]

group_b = ["investment", "portfolio", "funding", "capital",
           "backing startups", "exited", "seed", "pre-seed"]

group_c = ["uae", "dubai", "abu dhabi", "middle east"]

group_d = ["founder", "chairman", "partner","principal", "managing director"]

uae_keywords = ["uae", "dubai", "abu dhabi", "emirates"]

mena_keywords = ["uae", "dubai", "abu dhabi", "emirates", "middle east", "mena"]

def classify_result(text):
    text = text.lower()
    if any(k in text for k in group_a):
        return "Green"
    if any(k in text for k in group_b) and any(k in text for k in group_c):
        return "Green"
    if any(k in text for k in group_b) or any(k in text for k in group_d):
        return "Red"
    return "Discard"

def score_result(text):
    text = text.lower()

    score = 1
    matched_keywords = []
    signal_breakdown = []

    if any(k in text for k in mena_keywords):
        signal_breakdown.append("MENA presence")
    else:
        return {
            "score": 1,
            "confidence": "Low",
            "matched_keywords": [],
            "signal_breakdown": ["No MENA signal"]
        }

    if any(k in text for k in uae_keywords):
        score += 6
        signal_breakdown.append("UAE presence")

    if any(k in text for k in group_a):
        score += 3
        signal_breakdown.append("Angel / Family Office signal")
    elif any(k in text for k in group_b):
        score += 2
        signal_breakdown.append("Investment activity signal")

    if any(k in text for k in group_d):
        score += 2
        signal_breakdown.append("Senior role/title")

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
        "matched_keywords": list(set([k for k in mena_keywords + group_a + group_b + group_d if k in text])),
        "signal_breakdown": signal_breakdown
    }

queries = [
    "angel investor UAE site:linkedin.com/in",
    "family office Dubai site:linkedin.com/in",
    "private investor Abu Dhabi site:linkedin.com/in",
    "early-stage investor Middle East site:linkedin.com/in"
]

results = []

if st.button("Run Discovery", key="run_discovery_button"):
    st.write("Button clicked")

    with DDGS(timeout=10) as ddgs:
        for query in queries:
            st.write("Running query:", query)
            for r in ddgs.text(query, max_results=5, backend="html"):
                title = r.get("title", "")
                snippet = r.get("body", "")
                url = r.get("href", "")

                combined_text = f"{title} {snippet}"
                scoring = score_result(combined_text)

                result_id = url.strip().lower()
                now = datetime.now(timezone.utc).isoformat()

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
                st.write("Found result:", title)

new_df = pd.DataFrame(results)
new_df = new_df.reindex(columns=internal_col)

if new_df.empty:
    st.info("No results found.")

if not existing_df.empty:
    combined_df = pd.concat([existing_df, new_df])
    combined_df = combined_df.drop_duplicates(subset="result_id", keep="first")
else:
    combined_df = new_df

if not combined_df.empty and len(new_df) > 0:
    combined_df.columns = [str(c) for c in combined_df.columns]
    display_df = combined_df.rename(columns=display_col)
    sheet_url = "https://docs.google.com/spreadsheets/d/13syl6pUSdsXQ1XNnN_WVCGlpWm-80n6at4pdjZSuoBU/edit#gid=0"
    sh = gc.open_by_url(sheet_url)
    worksheet = sh.worksheet("Sheet1")
    values = [display_df.columns.values.tolist()] + display_df.values.tolist()
    worksheet.clear()
    worksheet.update(values)
    st.success(f"{len(new_df)} results found. Total results: {len(combined_df)}")
else:
    st.warning("Nothing new found.")

if "combined_df" in locals() and not combined_df.empty and "first_seen" in combined_df.columns:
    st.dataframe(
        combined_df.sort_values("first_seen", ascending=False),
        use_container_width=True
    )
else:
    st.info("No data to display yet. Click the 'Run Discovery' button.")
