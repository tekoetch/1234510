import streamlit as st
from ddgs import DDGS
import pandas as pd

st.set_page_config(page_title="Leads Dashboard + Scoring Playground", layout="wide")
st.title("Leads Discovery + Scoring Playground")

freeze_scoring = st.toggle("Freeze scoring (manual review mode)", value=False)

st.sidebar.header("Scoring Controls")

BASE_SCORE = st.sidebar.slider("Base score", 0.0, 3.0, 1.5, 0.1)

IDENTITY_WEIGHT = st.sidebar.slider("Identity keyword weight", 0.2, 3.0, 1.2, 0.1)
BEHAVIOR_WEIGHT = st.sidebar.slider("Behavior keyword weight", 0.1, 2.0, 0.4, 0.1)
SENIORITY_WEIGHT = st.sidebar.slider("Seniority keyword weight", 0.2, 3.0, 1.0, 0.1)

IDENTITY_GROUP_BONUS = st.sidebar.slider("Identity group bonus", 0.0, 2.0, 0.8, 0.1)
BEHAVIOR_GROUP_BONUS = st.sidebar.slider("Behavior group bonus", 0.0, 2.0, 0.6, 0.1)
SENIORITY_GROUP_BONUS = st.sidebar.slider("Seniority group bonus", 0.0, 2.0, 0.7, 0.1)
GEO_GROUP_BONUS = st.sidebar.slider("Geography group bonus", 0.0, 2.0, 0.9, 0.1)
IDENTITY_DIMINISHING_WEIGHT = st.sidebar.slider("Identity diminishing boost", 0.2, 1.5, 0.6, 0.1)


identity_keywords = [
    "angel investor", "angel investing", "family office",
    "venture partner", "chief investment officer", "cio",
    "founder", "co-founder", "ceo"
]

behavior_keywords = [
    "invested in", "investing in", "portfolio",
    "seed", "pre-seed", "early-stage", "funding", "fundraising"
]

seniority_keywords = [
    "partner", "managing director", "chairman",
    "board member", "advisor", "advisory"
]

uae_keywords = ["uae", "dubai", "abu dhabi", "emirates"]
mena_keywords = ["mena", "middle east", "gulf"]

def score_text(text, query):
    text = text.lower()
    query = query.lower()

    score = BASE_SCORE
    breakdown = []
    breakdown.append(f"Base score from query (+{BASE_SCORE})")
    signal_groups = set()

    uae_hit_text = any(k in text for k in uae_keywords)
    mena_hit_text = any(k in text for k in mena_keywords)
    uae_hit_query = any(k in query for k in uae_keywords)
    mena_hit_query = any(k in query for k in mena_keywords)

    if uae_hit_query:
        score += 0.3
        breakdown.append("UAE mentioned in query (+0.3)")

    if mena_hit_query:
        score += 0.2
        breakdown.append("MENA mentioned in query (+0.2)")

    if uae_hit_text:
        score += 1.2
        signal_groups.add("Geography")
        breakdown.append("UAE mentioned in text (+1.2)")

    elif mena_hit_text:
        score += 0.6
        signal_groups.add("Geography")
        breakdown.append("MENA mentioned in text (+0.6)")

    identity_hits = [k for k in identity_keywords if k in text]

    if identity_hits:
        first_hit = identity_hits[0]
        score += IDENTITY_WEIGHT
        breakdown.append(f"Primary identity '{first_hit}' (+{IDENTITY_WEIGHT})")

        for k in identity_hits[1:]:
            score += IDENTITY_DIMINISHING_WEIGHT
            breakdown.append(
                f"Additional identity '{k}' (+{IDENTITY_DIMINISHING_WEIGHT})"
            )

        signal_groups.add("Identity")


    behavior_hits = [k for k in behavior_keywords if k in text]
    for k in behavior_hits:
        score += BEHAVIOR_WEIGHT
        breakdown.append(f"Behavior keyword '{k}' (+{BEHAVIOR_WEIGHT})")

    if behavior_hits:
        score += BEHAVIOR_GROUP_BONUS
        signal_groups.add("Behavior")
        breakdown.append(f"Behavior group bonus (+{BEHAVIOR_GROUP_BONUS})")

    seniority_hits = [k for k in seniority_keywords if k in text]
    for k in seniority_hits:
        score += SENIORITY_WEIGHT
        breakdown.append(f"Seniority keyword '{k}' (+{SENIORITY_WEIGHT})")

    if seniority_hits:
        score += SENIORITY_GROUP_BONUS
        signal_groups.add("Seniority")
        breakdown.append(f"Seniority group bonus (+{SENIORITY_GROUP_BONUS})")

    if "Geography" in signal_groups:
        score += GEO_GROUP_BONUS
        breakdown.append(f"Geography group bonus (+{GEO_GROUP_BONUS})")

    score = min(score, 10.0)

    group_count = len(signal_groups)
    confidence = "High" if group_count >= 3 else "Medium" if group_count == 2 else "Low"

    breakdown.insert(0, f"Signal groups fired: {group_count}")

    return score, confidence, breakdown

st.subheader("Manual Scoring Playground")

sample_text = st.text_area(
    "Paste LinkedIn title + snippet",
    height=150,
    placeholder="Angel Investor | Based in Dubai | Investing in early-stage startups"
)

if sample_text:
    if freeze_scoring:
        score, confidence, breakdown = 0, "Manual", ["Scoring frozen"]
    else:
        score, confidence, breakdown = score_text(sample_text, "")

    st.metric("Score (1–10)", score)
    st.metric("Confidence", confidence)

    with st.expander("Why this scored what it scored"):
        for b in breakdown:
            st.write(b)

queries = [
    '"angel investor" UAE site:linkedin.com/in',
    '"family office" Dubai site:linkedin.com/in'
]

st.subheader("Live Discovery")

results = []

if st.button("Run Discovery"):
    with DDGS(timeout=10) as ddgs:
        for query in queries:
            for r in ddgs.text(query, max_results=5, backend="html"):
                title = r.get("title", "")
                snippet = r.get("body", "")
                url = r.get("href", "")

                combined_text = f"{title} {snippet}"

                if freeze_scoring:
                    score, confidence, breakdown = 0, "Manual", ["Scoring frozen"]
                else:
                    score, confidence, breakdown = score_text(combined_text, query)

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
        st.bar_chart(df["Score"].round(1).value_counts().sort_index())
