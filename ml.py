import streamlit as st
import pandas as pd
import numpy as np
import joblib # This is the tool that saves the "Brain" file
import os

# The "Heavy Machinery" for Machine Learning
from xgboost import XGBRegressor
from sklearn.multioutput import MultiOutputRegressor

# Your existing logic files
import first_pass
import second_pass

st.set_page_config(page_title="Investor ML Engine", layout="wide")

st.title("🚀 Professional Investor ML Trainer")
st.write("This tool turns your manual 1-10 ratings into a custom AI model.")

# --- STEP 1: DATA PREPARATION ---
st.header("Step 1: Process Raw Data for Review")
st.info("Upload your raw data. I will run the First and Second Pass rules and give you a CSV to label.")

uploaded_raw = st.file_uploader("Upload Raw_Leads.csv", type=["csv"])

if uploaded_raw is not None:
    # Load the file
    raw_df = pd.read_csv(uploaded_raw)
    
    if st.button("🔧 Generate Training Sheet"):
        rows_for_csv = []
        
        # We use a simple loop so you can see every step
        for index, row in raw_df.iterrows():
            # 1. Get the basic info
            name = str(row.get("Name", ""))
            title = str(row.get("Title", ""))
            snippet = str(row.get("Snippet", ""))
            url = str(row.get("URL", ""))
            p2_text = str(row.get("Pass_2_Text", ""))
            
            # 2. Run First Pass Logic (from your first_pass.py)
            combined_p1 = title + " " + snippet
            fp_score, fp_conf, fp_signals, fp_comp = first_pass.score_text(combined_p1, name, url)
            
            # 3. Run Second Pass Logic (from your second_pass.py)
            # We need to setup a 'state' dictionary like your script expects
            state = {
                "linkedin_hits": 0,
                "domain_hits": set(),
                "identity_confirmed": False,
                "geo_hits": 0,
                "expected_name": name.lower()
            }
            sp_score, sp_signals, _ = second_pass.score_second_pass(p2_text, url, state)
            
            # 4. Create the "Big Row" for your manual review
            # This contains all the "Raw" info and "Signals" detected
            new_entry = {
                "Name": name,
                "URL": url,
                "FP_Score": round(fp_score, 1),
                "FP_Signals": ", ".join(fp_signals),
                "SP_Score": round(sp_score, 1),
                "SP_Signals": ", ".join(sp_signals),
                "Raw_Text_Combined": combined_p1 + " | " + p2_text,
                # --- YOUR MANUAL 1-10 LABELS START HERE ---
                "LABEL_Identity": 1,   # Grade 1-10
                "LABEL_Behavior": 1,   # Grade 1-10
                "LABEL_Geo": 1,        # Grade 1-10
                "LABEL_Contact": 1     # New: Grade 1-10 based on how easy to find
            }
            rows_for_csv.append(new_entry)
            
        # Convert to a Table
        final_training_df = pd.DataFrame(rows_for_csv)
        st.write("### Review your data below:")
        st.dataframe(final_training_df)
        
        # Download Button
        csv_data = final_training_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download This for Manual Labeling",
            data=csv_data,
            file_name="ready_to_label.csv",
            mime="text/csv"
        )

st.divider()

# --- STEP 2: TRAINING THE BRAIN ---
st.header("Step 2: Train the ML Model")
st.write("Once you have filled in your 1-10 scores in Excel, upload that file here.")

labeled_file = st.file_uploader("Upload ready_to_label.csv (with your 1-10 scores)", type=["csv"])

if labeled_file is not None:
    data = pd.read_csv(labeled_file)
    
    if st.button("🧠 Train My AI Model"):
        # A. PREPARE THE "INPUTS" (X)
        # We tell the AI to look at the automated scores we generated earlier
        X = data[["FP_Score", "SP_Score"]]
        
        # B. PREPARE THE "TARGETS" (y)
        # These are your manual 1-10 grades
        y = data[["LABEL_Identity", "LABEL_Behavior", "LABEL_Geo", "LABEL_Contact"]]
        
        # C. CREATE THE MODEL
        # We use a Regressor because we want a number (1-10), not a Yes/No.
        base_model = XGBRegressor(
            n_estimators=100, 
            learning_rate=0.1, 
            max_depth=4, 
            random_state=42
        )
        
        # We wrap it so it can predict all 4 labels at once
        multi_model = MultiOutputRegressor(base_model)
        
        # D. TRAIN
        multi_model.fit(X, y)
        
        # E. SAVE THE MODEL
        # This creates the .pkl file you need for your main app
        joblib.dump(multi_model, "investor_brain.pkl")
        
        st.success("🎉 Success! The AI has learned your scoring style and saved 'investor_brain.pkl'.")
        
        # Download button for the file (to put on GitHub)
        with open("investor_brain.pkl", "rb") as f:
            st.download_button("Download investor_brain.pkl", f, "investor_brain.pkl")
