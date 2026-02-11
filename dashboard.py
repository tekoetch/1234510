import streamlit as st
import pandas as pd
import time
from ddgs import DDGS
from first_pass import score_text, identity_keywords, behavior_keywords, uae_keywords, mena_keywords, seniority_keywords
import second_pass

# --- UI STYLING ---
def inject_custom_css():
    st.markdown("""
        <style>
        /* Modern Font and Background */
        .main { background-color: #f8f9fa; }
        div.stButton > button {
            background-color: #007bff; color: white; border-radius: 8px;
            height: 3em; width: 100%; font-weight: bold; border: none;
        }
        /* Card Styling for Results */
        .metric-card {
            background: white; padding: 20px; border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05); text-align: center;
        }
        /* Badge Styling */
        .badge {
            padding: 4px 10px; border-radius: 20px; font-size: 11px;
            font-weight: bold; margin-right: 5px; display: inline-block;
        }
        .badge-id { background: #e3f2fd; color: #1976d2; }
        .badge-geo { background: #e8f5e9; color: #2e7d32; }
        .badge-sen { background: #fff3e0; color: #ef6c00; }
        </style>
    """, unsafe_allow_html=True)

def extract_found_keywords(text, keyword_list):
    """Helper to find which specific keywords triggered the match."""
    found = [k for k in keyword_list if k.lower() in str(text).lower()]
    return ", ".join(list(set(found))).upper()

def run_dashboard():
    inject_custom_css()
    st.title("Leads dashboard")

    # Initialize session state to store leads so they append and persist
    if 'all_leads' not in st.session_state:
        st.session_state['all_leads'] = []

    # Layout for Input
    c1, c2 = st.columns([3, 1])
    query = c1.text_input("Enter Search Keywords (e.g., 'Angel Investors Dubai')", placeholder="Dubai Venture Capitalists...")
    run_btn = c2.button("Run Deep Discovery")

    if run_btn and query:
        progress_bar = st.progress(0)
        log_area = st.empty()
        
        with DDGS() as ddgs:
            log_area.info(f"🔍 Executing global search for: {query}...")
            # Limit to 15 for a fast demo
            search_results = list(ddgs.text(query, max_results=15))
            
            for i, r in enumerate(search_results):
                name = r.get("title", "").split("-")[0].strip()
                log_area.markdown(f"**Processing:** {name}...")
                
                # 1. First Pass
                fp_score, fp_breakdown, _, fp_enriched = score_text(r['body'], query, r['href'])
                
                # 2. Second Pass (if FP is decent)
                sp_score = 0.0
                if fp_score >= 4.0:
                    log_area.warning(f"High Potential Found: {name}. Running Verification...")
                    # Simulating deep lookup/second pass
                    sp_score, _ = second_pass.score_text(r['body'], r['href'], {})
                
                # Keyword Extraction for the "Clean Table"
                combined_text = (r['title'] + " " + r['body']).lower()
                
                # Create result entry
                entry = {
                    "Name": name,
                    "Identity": extract_found_keywords(combined_text, identity_keywords),
                    "Seniority": extract_found_keywords(combined_text, seniority_keywords),
                    "Geography": extract_found_keywords(combined_text, uae_keywords + mena_keywords),
                    "Final Score": round((fp_score + sp_score), 1),
                    "Verdict": "GREAT" if (fp_score + sp_score) > 8 else ("GOOD" if (fp_score + sp_score) > 5 else "NOISE")
                }
                
                # Append to the session state list
                st.session_state['all_leads'].append(entry)
                
                progress_bar.progress((i + 1) / len(search_results))
                time.sleep(0.1) # Smoothness for the demo

        log_area.success("Discovery Complete!")

    # Display results if any exist in session state
    if st.session_state['all_leads']:
        df = pd.DataFrame(st.session_state['all_leads'])

        # --- Dashboard Metrics ---
        st.divider()
        m1, m2, m3 = st.columns(3)
        m1.metric("Leads Analyzed", len(df))
        
        # Qualified leads logic: Both 'GREAT' and 'GOOD' added together
        qualified_count = len(df[df['Verdict'].isin(['GREAT', 'GOOD'])])
        m2.metric("High Quality (Green)", qualified_count)
        
        m3.metric("Review Needed", len(df[df['Verdict'] == 'GOOD']))

        # --- Filters ---
        show_green = st.toggle("Filter: Show Green List Only", value=False)
        if show_green:
            # Filtering for the "Green List" includes both GREAT and GOOD as per instructions
            df = df[df['Verdict'].isin(['GREAT', 'GOOD'])]

        # --- Final Presentation Table ---
        st.subheader("Extracted Lead Intelligence")
        
        # Removed the "Confidence" ProgressColumn as it was confusing/incorrectly scaled
        st.dataframe(
            df[["Name", "Final Score", "Identity", "Seniority", "Geography", "Verdict"]].sort_values("Final Score", ascending=False),
            use_container_width=True,
            column_config={
                "Verdict": st.column_config.TextColumn("Status")
            }
        )
