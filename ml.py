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
    # Fix: Fetching keys with case-insensitivity
    t_val = str(row.get('Title', row.get('title', ''))).lower()
    s_val = str(row.get('Snippet', row.get('snippet', ''))).lower()
    combined_text = f"{t_val} {s_val}"

    # IDENTITY ESTIMATE
    est_id = 1
    # Strong signals in title text
    if any(k in t_val for k in ["angel investor", "founding partner", "managing partner", "family office"]):
        est_id = 9
    elif any(k in t_val for k in ["ceo", "private equity", "partner", "incubator", "angel", "founder", "co-founder"]):
        est_id = 8
    # Substring check in signal list (Fixed)
    elif any("Identity" in str(s) for s in fp_signals):
        est_id = 7
    
    # BEHAVIOR ESTIMATE
    est_beh = 1
    if any(k in combined_text for k in ["portfolio", "invested in", "funding", "exits", "series a", "seed"]):
        est_beh = 8
    # Substring check in signal list (Fixed)
    elif any("Behavior" in str(s) for s in fp_signals) or any("Behavior" in str(s) for s in sp_signals):
        est_beh = 7
    elif sp_score > 3.0: 
        est_beh = 5

    # GEOGRAPHY ESTIMATE
    est_geo = 1
    if any(k in combined_text for k in ["dubai", "abu dhabi", "uae", "united arab emirates"]):
        est_geo = 10
    elif any(k in combined_text for k in ["middle east", "emirates", "mena", "gcc"]):
        est_geo = 9
    # Substring check in signal list (Fixed)
    elif any("Geography" in str(s) for s in fp_signals) or any("Geography" in str(s) for s in sp_signals):
        est_geo = 8
    elif any("UAE LinkedIn domain (+0.6)" in str(s) for s in fp_signals):
        est_geo = 7    
    
    # Penalty for mismatch
    if any(k in combined_text for k in ["new york", "london", "india", "united states"]):
        if est_geo < 8:
            est_geo = 2

    return est_id, est_beh, est_geo

def clean_key(text):
    return text.strip().upper().replace(" ", "_")

def build_feature_vector(fp_signals, sp_signals, expected_columns=None):
    """
    Builds consistent binary feature vector.
    If expected_columns is provided, ensures perfect alignment.
    """
    features = {}

    for sig in fp_signals:
        key = f"FP_HAS_{clean_key(sig)}"
        features[key] = 1

    for sig in sp_signals:
        key = f"SP_HAS_{clean_key(sig)}"
        features[key] = 1

    df = pd.DataFrame([features]).fillna(0)

    # If training phase → no expected columns yet
    if expected_columns is None:
        return df

    # If inference phase → force alignment
    for col in expected_columns:
        if col not in df.columns:
            df[col] = 0

    return df[expected_columns]


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
            title = str(row.get("Title", row.get("title", "")))
            snippet = str(row.get("Snippet", row.get("snippet", "")))
            url = str(row.get("URL", row.get("url", "")))
            name = extract_name(title)
            if not name or len(name.split()) < 2:
                continue

            # Run Logic
            combined_text = f"{title} {snippet}"
            fp_score, _, fp_signals, _ = first_pass.score_text(combined_text, name, url)
            
            state = {"linkedin_hits": 0, "domain_hits": set(), "identity_confirmed": False, "geo_hits": 0, "expected_name": name.lower()}
            sp_score, sp_signals, _ = second_pass.score_second_pass(combined_text, url, state)

            feature_df = build_feature_vector(fp_signals, sp_signals)
            binary_feats = feature_df.iloc[0].to_dict()

            est_id, est_beh, est_geo = estimate_manual_labels(row, fp_score, sp_score, fp_signals, sp_signals)

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
    labeled_file = st.file_uploader("Upload labeled CSV", type=["csv"])

    if labeled_file and st.button("Train Model"):
        data = pd.read_csv(labeled_file)
        label_cols = ["LABEL_Identity", "LABEL_Behavior", "LABEL_Geo"]
        X = data.drop(columns=label_cols).select_dtypes(include=["number"])
        y = data[label_cols]

        model = MultiOutputRegressor(XGBRegressor(n_estimators=150, max_depth=5, learning_rate=0.07, random_state=42))
        model.fit(X, y)
        model_package = {
        "model": model,
        "feature_columns": X.columns.tolist()
    }

    joblib.dump(model_package, "investor_brain.pkl")

    st.success("Model trained successfully")
    with open("investor_brain.pkl", "rb") as f:
        st.download_button("Download investor_brain.pkl", f, file_name="investor_brain.pkl")
