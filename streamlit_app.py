import streamlit as st
from ddgs import DDGS
import pandas as pd

st.set_page_config(page_title="Leads Dashboard + Scoring Playground", layout="wide")
st.title("Leads Discovery + Scoring Playground")

freeze_scoring = st.toggle(
    "Freeze scoring (manual review mode)",
    value=False,
    help="When on, scores are not recalculated"
)

identity_keywords = [
    "angel investor",
    "angel investing",
    "family office",
    "venture partner",
    "chief investment officer",
    "cio",
    "founder",
    "co-founder",
    "ceo"
]

behavior_keywords = [
    "invested in",
    "investing in",
    "portfolio",
    "seed",
    "pre-seed",
    "early-stage",
    "funding",
    "fundraising"
]

seniority_keywords = [
    "partner",
    "managing director",
    "chairman",
    "board member",
    "advisor",
    "advisory"
]

uae_keywords = ["uae", "dubai", "abu dhabi", "emirates"]
mena_keywords = ["middle east", "mena"]

def score_text(text, query):
    text = text.lower()
    query = query.lower()

    score = 1.0
    signal_groups_fired = set()
    breakdown = []

    geo_hit = False

    if any(k in query for k in uae_keywords + mena_keywords):
        score += 0.3
        geo_hit = True
        breakdown.append("Query mentions MENA/UAE")

    if any(k in text for k in uae_keywords + mena_keywords):
        score += 0.7
        geo_hit = True
        breakdown.append("Text mentions MENA/UAE")

    if geo_hit:
        signal_groups_fired.add("Geography")

    identity_hits = [k for k in identity_keywords if k in text]
    if identity_hits:
        score += 2.0
        score += max(0, len(identity_hits) - 1) * 0.3
        signal_groups_fired.add("Identity")
        breakdown.append(f"Identity keywords: {', '.join(identity_hits)}")

    behavior_hits = [k for k in behavior_keywords if k in text]
    if behavior_hits:
        score += len(behavior_hits) * 0.3
        signal_groups_fired.add("Behavior")
        breakdown.append(f"Behavior keywords: {', '.join(behavior_hits)}")

    seniority_hits = [k for k in seniority_keywords if k in text]
    if seniority_hits:
        score += 1.5
        score += max(0, len(seniority_hits) - 1) * 0.2
        signal_groups_fired.add("Seniority")
        breakdown.append(f"Seniority keywords: {', '.join(seniority_hits)}")

    score = round(min(score, 10), 1)

    group_count = len(signal_groups_fired)

    if group_count >= 3:
        confidence = "High"
    elif group_count == 2:
        confidence = "Medium"
    else:
        confidence = "Low"

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

    st.metric("Score", score)
    st.metric("Confidence", confidence)

    with st.expander("Why this scored what it scored"):
        for b in breakdown:
            st.markdown(f"- {b}")

queries = [
    '"angel investor" UAE site:linkedin.com/in'
]    

st.subheader("Live Discovery")

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
        st.bar_chart(df["Score"].value_counts().sort_index())
