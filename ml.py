import streamlit as st
import pandas as pd
import joblib

from xgboost import XGBRegressor
from sklearn.multioutput import MultiOutputRegressor

import first_pass
import second_pass

def extract_name(title):
    for sep in [" - ", " | ", " – ", " — "]:
        if sep in title:
            return title.split(sep)[0].strip()
    return title.strip()

# --- HEURISTIC AUTO-FILL LOGIC ---
def estimate_manual_labels(row, fp_score, sp_score, fp_signals, sp_signals):

    # IDENTITY ESTIMATE
    est_id = 1
    # Strong signals
    if any(k in row.get('Title','').lower() for k in ["angel investor", "founding partner", "managing partner"]):
        est_id = 9
    elif any(k in row.get('Title','').lower() for k in ["investor", "venture capital", "private equity"]):
        est_id = 7
    # Keyword boosts
    elif "Identity" in fp_signals:
        est_id = 6
    
    # BEHAVIOR ESTIMATE
    est_beh = 1
    # Look for active words in snippets
    combined_text = (row.get('Snippet', '') + " " + row.get('Pass_2_Text', '')).lower()
    if any(k in combined_text for k in ["portfolio", "invested in", "ticket size", "exits"]):
        est_beh = 8
    elif "Behavior" in fp_signals or "Behavior" in sp_signals:
        est_beh = 6
    elif sp_score > 3.0: # If second pass found something relevant
        est_beh = 5

    # GEOGRAPHY ESTIMATE
    est_geo = 1
    # Explicit city mentions are gold
    if any(k in combined_text for k in ["dubai", "abu dhabi", "riyadh"]):
        est_geo = 10
    elif any(k in combined_text for k in ["uae", "emirates", "mena", "gcc"]):
        est_geo = 8
    elif "Geography" in fp_signals:
        est_geo = 7
    elif "Geography" in sp_signals:
        est_geo = 6
    
    # Penalties for clearly wrong locations
    if any(k in combined_text for k in ["new york", "london", "singapore", "india", "united states"]):
        if est_geo < 8: # Only penalize if not explicitly also mentioning Dubai
            est_geo = 2

    return est_id, est_beh, est_geo

def extract_binary_features(fp_signals, sp_signals):
    features = {}

    for sig in fp_signals:
        key = f"FP_HAS_{sig.upper().replace(' ', '_')}"
        features[key] = 1

    for sig in sp_signals:
        key = f"SP_HAS_{sig.upper().replace(' ', '_')}"
        features[key] = 1

    return features


def run_ml_trainer():
    st.title("Investor ML Trainer")
    st.write("Generate a labeling sheet, score it manually, and train a custom model.")

    st.header("Step 1: Generate labeling sheet")

    raw_file = st.file_uploader(
        "Upload CSV with Title, Snippet, URL",
        type=["csv"]
    )

    if raw_file and st.button("Generate Sheet"):
        raw_df = pd.read_csv(raw_file)
        rows = []

        for _, row in raw_df.iterrows():
            title = str(row.get("Title", ""))
            snippet = str(row.get("Snippet", ""))
            url = str(row.get("URL", ""))
            name = extract_name(title)
            if not name or len(name.split()) < 2:
                continue

            # ---- First Pass ----
            combined_text = f"{title} {snippet}"
            fp_score, _, fp_signals, _ = first_pass.score_text(
                combined_text, name, url
            )

            # ---- Second Pass ----
            state = {
                "linkedin_hits": 0,
                "domain_hits": set(),
                "identity_confirmed": False,
                "geo_hits": 0,
                "expected_name": name.lower()
            }

            sp_score, sp_signals, _ = second_pass.score_second_pass(
                combined_text, url, state
            )

            # ---- Binary ML features ----
            binary_feats = extract_binary_features(fp_signals, sp_signals)

            est_id, est_beh, est_geo = estimate_manual_labels(row, fp_score, sp_score, fp_signals, sp_signals)

            # ---- Final row ----
            entry = {
                "Name": name,
                "Title": title,
                "Snippet": snippet,
                "URL": url,
                "FP_Score": round(fp_score, 2),
                "SP_Score": round(sp_score, 2),
                "FP_Signals": ", ".join(fp_signals),
                "SP_Signals": ", ".join(sp_signals),
                **binary_feats,
                # Manual labels 
                "LABEL_Identity": est_id,
                "LABEL_Behavior": est_beh,
                "LABEL_Geo": est_geo
            }

            rows.append(entry)

        df = pd.DataFrame(rows).fillna(0)

        st.success("Labeling sheet generated")
        st.dataframe(df, use_container_width=True)

        st.download_button(
            "Download ready_to_label.csv",
            df.to_csv(index=False),
            file_name="ready_to_label.csv"
        )

    st.divider()

    st.header("Step 2: Train ML model")

    labeled_file = st.file_uploader(
        "Upload labeled CSV (with 1–10 scores filled in)",
        type=["csv"]
    )

    if labeled_file and st.button("Train Model"):
        data = pd.read_csv(labeled_file)

        label_cols = [
            "LABEL_Identity",
            "LABEL_Behavior",
            "LABEL_Geo",
        ]

        X = data.drop(columns=label_cols)
        X = X.select_dtypes(include=["number"])
        y = data[label_cols]

        model = MultiOutputRegressor(
            XGBRegressor(
                n_estimators=150,
                max_depth=5,
                learning_rate=0.07,
                random_state=42
            )
        )

        model.fit(X, y)
        joblib.dump(model, "investor_brain.pkl")

        st.success("Model trained successfully")

        with open("investor_brain.pkl", "rb") as f:
            st.download_button(
                "Download investor_brain.pkl",
                f,
                file_name="investor_brain.pkl"
            )
