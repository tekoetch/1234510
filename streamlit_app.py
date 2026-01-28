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

identity_keywords = [
    "angel investor",
    "angel investors",
    "angel investing",
    "ceo",
    "founder",
    "co-founder",
    "chief investment officer",
    "head of family office",
    "investment office"
]

behavior_keywords = [
    "invested in",
    "startup mentor",
    "startup builder",
    "startup",
    "start up",
    "startup space",
    "seed",
    "seed funding",
    "seed capital",
    "pre-seed",
    "fundraising"
]

seniority_keywords = [
    "partner",
    "founding member",
    "strategic advisory",
    "business builder"
]

uae_keywords = ["uae", "dubai", "abu dhabi", "emirates"]
mena_keywords = ["uae", "dubai", "abu dhabi", "emirates", "middle east", "mena"]

def count_hits(text, keywords):
    return sum(text.count(k) for k in keywords)

def score_text(text, query_used, weights):
    text = text.lower()
    query_used = query_used.lower()

    score = 1
    signal_breakdown = []

    mena_in_text = any(k in text for k in mena_keywords)
    mena_in_query = any(k in query_used for k in mena_keywords)

    if mena_in_text or mena_in_query:
        score += weights["mena"]
        signal_breakdown.append("MENA relevance")

    signal_breakdown.append("MENA presence")

    if any(k in text for k in uae_keywords):
        score += weights["uae"]
        signal_breakdown.append("UAE context")

    identity_hits = count_hits(text, identity_keywords)
    behavior_hits = count_hits(text, behavior_keywords)
    seniority_hits = count_hits(text, seniority_keywords)

    if identity_hits:
        score += identity_hits * weights["identity"]
        signal_breakdown.append(f"Identity signals ×{identity_hits}")

    if behavior_hits:
        score += behavior_hits * weights["behavior"]
        signal_breakdown.append(f"Behavior signals ×{behavior_hits}")

    if seniority_hits:
        score += seniority_hits * weights["seniority"]
        signal_breakdown.append(f"Seniority signals ×{seniority_hits}")

    score = round(min(score, 10))

    if score >= 7:
        confidence = "High"
    elif score >= 4:
        confidence = "Medium"
    else:
        confidence = "Low"

    return score, confidence, signal_breakdown

st.sidebar.header("Scoring Playground")

weights = {
    "identity": st.sidebar.slider("Identity (Angel / Founder / CIO)", 0.0, 3.0, 1.5, 0.1),
    "behavior": st.sidebar.slider("Investment Behavior (per hit)", 0.0, 1.0, 0.3, 0.1),
    "seniority": st.sidebar.slider("Seniority / Advisory", 0.0, 1.5, 0.5, 0.1),
    "uae": st.sidebar.slider("UAE Context Boost", 0.0, 1.5, 0.7, 0.1),
    "mena": st.sidebar.slider("MENA Boost", 0.0, 1.0, 0.4, 0.1),
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
