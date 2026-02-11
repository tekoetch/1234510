import streamlit as st
import pandas as pd
import joblib
import re
import numpy as np

from xgboost import XGBRegressor
from sklearn.multioutput import MultiOutputRegressor

import first_pass
import second_pass

def extract_name(title):
    for sep in [" - ", " | ", " – ", " — "]:
        if sep in title:
            return title.split(sep)[0].strip()
    return title.strip()

# --- 1. THE "MASTER" CLEANER (REGEX) ---
def clean_key(text):
    """
    Forces all feature keys to be UPPERCASE_WITH_UNDERSCORES only.
    Removes + . ( ) ' and other junk.
    Example: "Identity (Angel) +2.5" -> "IDENTITY_ANGEL_2_5"
    """
    # 1. Force uppercase
    s = str(text).upper()
    # 2. Regex: Replace anything that is NOT A-Z or 0-9 with '_'
    s = re.sub(r'[^A-Z0-9]+', '_', s)
    # 3. Remove leading/trailing underscores
    return s.strip('_')

def extract_binary_features(fp_signals, sp_signals):
    """
    Extracts binary features using the Master Cleaner.
    This function is imported by streamlit_app2.py to ensure EXACT MATCHING.
    """
    features = {}
    
    # Handle list input (from live app) or string input (from CSV)
    if isinstance(fp_signals, str):
        fp_list = [s.strip() for s in fp_signals.split(", ") if s.strip()]
    else:
        fp_list = fp_signals

    if isinstance(sp_signals, str):
        sp_list = [s.strip() for s in sp_signals.split(", ") if s.strip()]
    else:
        sp_list = sp_signals

    for sig in fp_list:
        key = f"FP_HAS_{clean_key(sig)}"
        features[key] = 1
        
    for sig in sp_list:
        key = f"SP_HAS_{clean_key(sig)}"
        features[key] = 1
        
    return features

# --- 2. LOGIC TO ESTIMATE LABELS (Auto-Fill) ---
def estimate_manual_labels(row, fp_score, sp_score, fp_signals, sp_signals):
    t_val = str(row.get('Title', row.get('title', ''))).lower()
    s_val = str(row.get('Snippet', row.get('snippet', ''))).lower()
    combined_text = f"{t_val} {s_val}"
    
    fp_str = str(fp_signals).lower()
    sp_str = str(sp_signals).lower()

    # IDENTITY
    est_id = 1
    if any(k in t_val for k in ["angel investor", "founding partner", "managing partner", "family office"]):
        est_id = 9
    elif any(k in t_val for k in ["investor", "venture capital", "private equity", "partner"]):
        est_id = 7
    elif "identity" in fp_str:
        est_id = 6
    
    # BEHAVIOR
    est_beh = 1
    if any(k in combined_text for k in ["portfolio", "invested in", "ticket size", "exits", "series a", "seed"]):
        est_beh = 8
    elif "behavior" in fp_str or "behavior" in sp_str:
        est_beh = 6
    elif sp_score > 3.0: 
        est_beh = 5

    # GEOGRAPHY
    est_geo = 1
    if any(k in combined_text for k in ["dubai", "abu dhabi", "riyadh", "uae", "emirates"]):
        est_geo = 10
    elif "uae linkedin domain" in fp_str:
        est_geo = 8
    elif "geography" in fp_str or "geography" in sp_str:
        est_geo = 7
    
    if any(k in combined_text for k in ["new york", "london", "india", "united states"]):
        if est_geo < 8: est_geo = 2

    return est_id, est_beh, est_geo

def run_ml_trainer():
    st.title("🤖 Self-Healing ML Trainer")
    st.write("Automatically cleans CSV headers and trains the model.")

    # --- TAB 1: GENERATE LABELING SHEET ---
    st.header("Step 1: Generate labeling sheet")
    raw_file = st.file_uploader("Upload Raw Leads CSV", type=["csv"])

    if raw_file and st.button("Generate Sheet"):
        raw_df = pd.read_csv(raw_file)
        rows = []
        for _, row in raw_df.iterrows():
            title = str(row.get("Title", row.get("title", "")))
            snippet = str(row.get("Snippet", row.get("snippet", "")))
            url = str(row.get("URL", row.get("url", "")))
            name = extract_name(title)
            if not name or len(name.split()) < 2: continue

            combined = f"{title} {snippet}"
            fp_score, _, fp_sigs, _ = first_pass.score_text(combined, name, url)
            state = {"linkedin_hits":0, "domain_hits":set(), "identity_confirmed":False, "geo_hits":0, "expected_name":name.lower()}
            sp_score, sp_sigs, _ = second_pass.score_second_pass(combined, url, state)

            binary_feats = extract_binary_features(fp_sigs, sp_sigs)
            est_id, est_beh, est_geo = estimate_manual_labels(row, fp_score, sp_score, fp_sigs, sp_sigs)

            entry = {
                "Name": name, "Title": title, "Snippet": snippet, "URL": url,
                "FP_Score": round(fp_score, 2), "SP_Score": round(sp_score, 2),
                "FP_Signals": ", ".join(fp_sigs), "SP_Signals": ", ".join(sp_sigs),
                **binary_feats,
                "LABEL_Identity": est_id, "LABEL_Behavior": est_beh, "LABEL_Geo": est_geo
            }
            rows.append(entry)

        df = pd.DataFrame(rows).fillna(0)
        st.dataframe(df.head())
        st.download_button("Download ready_to_label.csv", df.to_csv(index=False), "ready_to_label.csv")

    st.divider()

    # --- TAB 2: TRAIN WITH AUTO-FIX ---
    st.header("Step 2: Fix Headers & Train")
    st.info("Upload your EXISTING labeled CSV (even with bad headers). I will fix it.")
    
    labeled_file = st.file_uploader("Upload Labeled CSV", type=["csv"], key="train")

    if labeled_file and st.button("Fix & Train Model"):
        data = pd.read_csv(labeled_file)
        
        # 1. Drop old binary columns (the ones with __ or bad chars)
        cols_to_drop = [c for c in data.columns if c.startswith("FP_HAS_") or c.startswith("SP_HAS_")]
        data_clean = data.drop(columns=cols_to_drop)
        
        # 2. Re-generate PERFECT binary columns from the Signals text
        st.write("🛠️ Cleaning feature names...")
        new_features = []
        
        for _, row in data_clean.iterrows():
            # Get the raw signal text strings
            fp_s = str(row.get("FP_Signals", ""))
            sp_s = str(row.get("SP_Signals", ""))
            
            # Use the robust extract_binary_features function
            feats = extract_binary_features(fp_s, sp_s)
            new_features.append(feats)
            
        feat_df = pd.DataFrame(new_features).fillna(0)
        data_final = pd.concat([data_clean.reset_index(drop=True), feat_df.reset_index(drop=True)], axis=1).fillna(0)
        
        # 3. Train
        label_cols = ["LABEL_Identity", "LABEL_Behavior", "LABEL_Geo"]
        # Drop non-numeric columns and labels to get X
        X = data_final.drop(columns=label_cols).select_dtypes(include=["number"])
        y = data_final[label_cols]

        model = MultiOutputRegressor(XGBRegressor(n_estimators=150, max_depth=5, learning_rate=0.07, random_state=42))
        model.fit(X, y)
        
        joblib.dump(model, "model.pkl")
        st.success(f"✅ Trained on {len(X.columns)} aligned features!")
        
        with open("model.pkl", "rb") as f:
            st.download_button("Download Fixed model.pkl", f, "model.pkl")
