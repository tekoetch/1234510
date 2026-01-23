import streamlit as st
from duckduckgo_search import DDGS
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Leads Dashboard", layout="wide")
st.title("Dashboard testing")

conn = st.connection("gsheets", type=GSheetsConnection)

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

group_a = ["angel investor", "angel investing", "family office",
           "private investor", "early-stage investor", "venture investor"
]

group_b = ["investment", "portfolio", "funding", "capital",
           "backing startups", "exited", "seed", "pre-seed"
]

group_c = ["uae", "dubai", "abu dhabi", "middle east"]

group_d = ["founder", "chairman", "partner","principal", "managing director"]

def classify_result(text):
    text = text.lower()

    if any(k in text for k in group_a):
        return "Green"

    if any(k in text for k in group_b) and any(k in text for k in group_c):
        return "Green"

    if any(k in text for k in group_b) or any(k in text for k in group_d):
        return "Red"

    return "Discard"

queries = [
    "angel investor UAE",
    "family office Dubai",
    "private investor Abu Dhabi",
    "early-stage investor Middle East"
]

results = []

if st.button("Run Discovery"):
    results = []

    with DDGS() as ddgs:
        for query in queries:
            for r in ddgs.text(query, max_results=20):
                title = r.get("title", "")
                snippet = r.get("body", "")
                url = r.get("href", "")

                combined_text = f"{title} {snippet}"
                classification = classify_result(combined_text)

                result_id = url.strip().lower()
                now = datetime.now(timezone.utc).isoformat()

                results.append({
                    "Result ID": result_id,
                    "Query Used": query,
                    "Title": title,
                    "Snippet": snippet,
                    "URL": url,
                    "Classification": classification,
                    "First Seen": now,
                    "Last Checked": now
                })

new_df = pd.DataFrame(results)

if not existing_df.empty:
    combined_df = pd.concat([existing_df, new_df])
    combined_df = combined_df.drop_duplicates(subset="Result ID", keep="first")
else:
    combined_df = new_df

conn.update(worksheet="Sheet1", data=combined_df)
st.success(f"Stored {len(new_df)} results. Total: {len(combined_df)}")

st.dataframe(
    combined_df.sort_values("First Seen", ascending=False),
    use_container_width=True
)
