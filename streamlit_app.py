import streamlit as st
from ddgs import DDGS
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timezone
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Leads Dashboard + Scoring Playground", layout="wide")
st.title("Leads Discovery + Scoring Playground")

conn = st.connection("gsheets", type=GSheetsConnection)

Scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_info = st.secrets["GCP_SERVICE_ACCOUNT_JSON"]
credentials = Credentials.from_service_account_info(creds_info, scopes=Scopes)
gc = gspread.authorize(credentials)

group_a = ["angel investor", "angel investing", "family office",
           "private investor", "early-stage investor", "venture investor"]

group_b = ["investment", "portfolio", "funding", "capital",
           "seed", "pre-seed"]

group_d = ["founder", "chairman", "partner", "principal", "managing director"]

uae_keywords = ["uae", "dubai", "abu dhabi", "emirates"]
mena_keywords = ["mena", "middle east", "uae", "dubai", "abu dhabi"]

def score_text(text, weights):
    text = text.lower()
    score = 1
    breakdown = []

    if any(k in text for k in mena_keywords):
        score += weights["mena"]
        breakdown.append("MENA presence")
    else:
        return score, "Low", ["No MENA signal"]

    if any(k in text for k in uae_keywords):
        score += weights["uae"]
        breakdown.append("UAE presence")

    if any(k in text for k in group_a):
        score += weights["angel"]
        breakdown.append("Angel / FO signal")
    elif any(k in text for k in group_b):
        score += weights["investment"]
        breakdown.append("Investment activity")

    if any(k in text for k in group_d):
        score += weights["seniority"]
        breakdown.append("Senior role")

    score = min(score, 10)

    if score >= 8:
        confidence = "High"
    elif score >= 5:
        confidence = "Medium"
    else:
        confidence = "Low"

    return score, confidence, breakdown

st.sidebar.header("🎛️ Scoring Playground")

weights = {
    "mena": st.sidebar.slider("MENA Weight", 0, 5, 1),
    "uae": st.sidebar.slider("UAE Weight", 0, 8, 6),
    "angel": st.sidebar.slider("Angel / FO Weight", 0, 5, 3),
    "investment": st.sidebar.slider("Investment Weight", 0, 5, 2),
    "seniority": st.sidebar.slider("Seniority Weight", 0, 5, 2),
}

freeze_scoring = st.sidebar.checkbox("Freeze scoring (no changes)", value=False)

st.subheader("🧪 Scoring Playground")

sample_text = st.text_area(
    "Paste a real LinkedIn title + snippet here",
    height=150,
    placeholder="Angel Investor | Based in Dubai | Early-stage FinTech & SaaS"
)

if sample_text:
    if freeze_scoring:
        st.warning("Scoring is frozen")
    score, confidence, breakdown = score_text(sample_text, weights)

    st.metric("Score", score)
    st.metric("Confidence", confidence)
    st.write("Signals:", " | ".join(breakdown))

queries = [
    '"angel investor" UAE site:linkedin.com/in',
    '"family office" Dubai site:linkedin.com/in',
]

st.subheader("🔍 Live Discovery")

results = []

if st.button("Run Discovery"):
    with DDGS(timeout=10) as ddgs:
        for query in queries:
            st.write("Running:", query)
            for r in ddgs.text(query, max_results=5, backend="html"):
                title = r.get("title", "")
                snippet = r.get("body", "")
                url = r.get("href", "")
                combined = f"{title} {snippet}"

                score, confidence, breakdown = score_text(combined, weights)

                results.append({
                    "Title": title,
                    "Snippet": snippet,
                    "URL": url,
                    "Score": score,
                    "Confidence": confidence,
                    "Signals": " | ".join(breakdown)
                })

    df = pd.DataFrame(results)
    st.dataframe(df, use_container_width=True)

    if not df.empty:
        st.bar_chart(df["Score"])
