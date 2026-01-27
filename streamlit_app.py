import streamlit as st
from ddgs import DDGS
import pandas as pd
from datetime import datetime, timezone

st.set_page_config(page_title="Leads Dashboard + Scoring Playground", layout="wide")
st.title("Leads Discovery + Scoring Playground")

freeze_scoring = st.toggle(
    "Freeze scoring (manual review mode)",
    value=False,
    help="When on, scores are not recalculated"
)

group_a = [
    "angel investor", "angel investing", "family office",
    "private investor", "early-stage investor", "venture investor"
]

group_b = [
    "investment", "portfolio", "funding", "capital",
    "seed", "pre-seed"
]

group_d = [
    "founder", "chairman", "partner",
    "principal", "managing director"
]

uae_keywords = ["uae", "dubai", "abu dhabi", "emirates"]
mena_keywords = ["uae", "dubai", "abu dhabi", "emirates", "middle east", "mena"]

def score_text(text, query_used, weights):
    text = text.lower()
    query_used = query_used.lower()

    score = 1
    signal_breakdown = []

    mena_in_text = any(k in text for k in mena_keywords)
    mena_in_query = any(k in query_used for k in mena_keywords)

    if mena_in_text or mena_in_query:
        signal_breakdown.append("MENA presence")
    else:
        return 1, "Low", ["No MENA signal"]

    if any(k in text for k in uae_keywords):
        score += weights["uae"]
        signal_breakdown.append("UAE presence")

    if any(k in text for k in group_a):
        score += weights["angel"]
        signal_breakdown.append("Angel / Family Office signal")
    elif any(k in text for k in group_b):
        score += weights["investment"]
        signal_breakdown.append("Investment activity signal")

    if any(k in text for k in group_d):
        score += weights["seniority"]
        signal_breakdown.append("Senior role/title")

    score = min(score, 10)

    if score >= 8:
        confidence = "High"
    elif score >= 5:
        confidence = "Medium"
    else:
        confidence = "Low"

    return score, confidence, signal_breakdown

st.sidebar.header("Scoring Playground")

weights = {
    "uae": st.sidebar.slider("UAE Weight", 0, 8, 6),
    "angel": st.sidebar.slider("Angel / FO Weight", 0, 5, 3),
    "investment": st.sidebar.slider("Investment Weight", 0, 5, 2),
    "seniority": st.sidebar.slider("Seniority Weight", 0, 5, 2),
}

st.subheader("Manual Scoring Playground")

sample_text = st.text_area(
    "Paste a real LinkedIn title + snippet here",
    height=150,
    placeholder="Angel Investor | Based in Dubai | Early-stage FinTech & SaaS"
)

if sample_text:
    if freeze_scoring:
        st.warning("Scoring is frozen")
        score, confidence, breakdown = 0, "Manual", ["Scoring frozen"]
    else:
        score, confidence, breakdown = score_text(sample_text, "", weights)

    st.metric("Score", score)
    st.metric("Confidence", confidence)

    with st.expander("Why this scored what it scored"):
        for s in breakdown:
            st.markdown(f"- Good {s}")

queries = [
    '"angel investor" UAE site:linkedin.com/in',
    '"family office" Dubai site:linkedin.com/in',
]

st.subheader("Live Discovery")

results = []

if st.button("Run Discovery"):
    with DDGS(timeout=10) as ddgs:
        for query in queries:
            st.write("Running query:", query)

            for r in ddgs.text(query, max_results=5, backend="html"):
                title = r.get("title", "")
                snippet = r.get("body", "")
                url = r.get("href", "")
                combined_text = f"{title} {snippet}"

                if freeze_scoring:
                    score, confidence, breakdown = 0, "Manual", ["Scoring frozen"]
                else:
                    score, confidence, breakdown = score_text(
                        combined_text,
                        query,
                        weights
                    )

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
        st.subheader("Score Distribution")
        st.bar_chart(df["Score"].value_counts().sort_index())
