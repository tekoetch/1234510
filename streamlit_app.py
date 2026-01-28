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
    found = {
        "MENA": [],
        "UAE": [],
        "IDENTITY": [],
        "BEHAVIOR": [],
        "SENIORITY": []
    }

    for k in mena_keywords:
        if k in text:
            found["MENA"].append(k)
    if found["MENA"]:
        signal_breakdown.append("MENA relevance")
    else:
        signal_breakdown.append("No MENA relevance")

    for k in uae_keywords:
        if k in text:
            found["UAE"].append(k)
    if found["UAE"]:
        score += 3
        signal_breakdown.append("UAE presence")

    for k in identity_keywords:
        if k in text:
            found["IDENTITY"].append(k)
    if found["IDENTITY"]:
        score += 3
        signal_breakdown.append("Investor identity signal")

    for k in behavior_keywords:
        if k in text:
            found["BEHAVIOR"].append(k)
    if found["BEHAVIOR"]:
        score += 2
        signal_breakdown.append("Investment activity signal")

    for k in seniority_keywords:
        if k in text:
            found["SENIORITY"].append(k)
    if found["SENIORITY"]:
        score += 2
        signal_breakdown.append("Senior role/title")

    score = min(score, 10)

    if score >= 8:
        confidence = "High"
    elif score >= 5:
        confidence = "Medium"
    else:
        confidence = "Low"

    readable_keywords = []
    for group, keys in found.items():
        if keys:
            readable_keywords.append(f"{group}: {', '.join(keys)}")

    return {
        "score": score,
        "confidence": confidence,
        "matched_keywords": " | ".join(readable_keywords),
        "signal_breakdown": " | ".join(signal_breakdown)
    }


queries = [
    '"angel investor" UAE site:linkedin.com/in',
    '"family office" Dubai site:linkedin.com/in'
]

results = []

if st.button("Run Discovery", key="run_discovery_button"):
    st.write("Button clicked")

    placeholder = st.empty()
    results_container = []

    with DDGS(timeout=10) as ddgs:
        total_results = 0

        for query in queries:
            placeholder.markdown(f"**Running query:** `{query}`")

            for r in ddgs.text(query, max_results=5, backend="html"):
                title = r.get("title", "")
                snippet = r.get("body", "")
                url = r.get("href", "")

                combined_text = f"{title} {snippet}"
                scoring = score_result(combined_text)

                result_id = url.strip().lower()
                now = datetime.now(timezone.utc).isoformat()

                results_container.append({
                    "result_id": result_id,
                    "query_used": query,
                    "title": title,
                    "snippet": snippet,
                    "url": url,
                    "first_seen": now,
                    "last_checked": now,
                    "score": scoring["score"],
                    "confidence_level": scoring["confidence"],
                    "matched_keywords": scoring["matched_keywords"],
                    "signal_breakdown": scoring["signal_breakdown"]
                })

                placeholder.markdown(
                    f"**Found result:** {title} | Score: {scoring['score']} | Confidence: {scoring['confidence']}"
                )
                total_results += 1

    new_df = pd.DataFrame(results_container)
    new_df = new_df.reindex(columns=internal_col)

    if not new_df.empty:
        if not existing_df.empty:
            combined_df = pd.concat([existing_df, new_df]).drop_duplicates(subset="result_id", keep="first")
        else:
            combined_df = new_df

        combined_df.columns = [str(c) for c in combined_df.columns]
        display_df = combined_df.rename(columns=display_col)

        sheet_url = "https://docs.google.com/spreadsheets/d/13syl6pUSdsXQ1XNnN_WVCGlpWm-80n6at4pdjZSuoBU/edit#gid=0"
        sh = gc.open_by_url(sheet_url)
        worksheet = sh.worksheet("Sheet1")
        values = [display_df.columns.values.tolist()] + display_df.values.tolist()
        worksheet.clear()
        worksheet.update(values)

        st.success(f"{len(new_df)} new leads added. Total: {len(combined_df)}")
        st.dataframe(combined_df.sort_values("first_seen", ascending=False), use_container_width=True)
    else:
        st.warning("Nothing new found.")
