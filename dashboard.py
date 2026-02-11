import streamlit as st
import pandas as pd
import time
import re
from ddgs import DDGS
from first_pass import score_text, identity_keywords, behavior_keywords, uae_keywords, mena_keywords, seniority_keywords
import second_pass

# --- UI STYLING ---
def inject_custom_css():
    st.markdown("""
        <style>
        /* Modern Font and Background */
        .main { background-color: #f8f9fa; }
        
        /* Metric Card Styling */
        div[data-testid="stMetric"] {
            background-color: white;
            border: 1px solid #e2e8f0;
            padding: 15px;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        }
        
        div.stButton > button {
            background-color: #007bff; color: white; border-radius: 8px;
            height: 3em; width: 100%; font-weight: bold; border: none;
        }

        /* Badge Styling for Table */
        .badge {
            padding: 4px 10px; border-radius: 20px; font-size: 11px;
            font-weight: bold; margin-right: 5px; display: inline-block;
        }
        </style>
    """, unsafe_allow_html=True)

def normalize_url(url):
    """Normalizes URLs to prevent duplicates based on query strings."""
    return url.split("?")[0].lower().strip()

def extract_found_keywords(text, keyword_list):
    """Identifies which keywords from a list appear in the text."""
    found = [k for k in keyword_list if k.lower() in str(text).lower()]
    return ", ".join(list(set(found))).upper()

def run_dashboard():
    inject_custom_css()
    st.title("Leads dashboard")

    if 'all_leads' not in st.session_state:
        st.session_state['all_leads'] = []

    st.write("Select a segment to run automated discovery:")
    c1, c2, c3 = st.columns(3)
    
    # Configuration for search queries
    search_type = None
    if c1.button("Angel Investors"):
        search_type = ("Angel Investors", '"angel investor" UAE site:linkedin.com/in')
    if c2.button("Family Office"):
        search_type = ("Family Office", '"family office" UAE site:linkedin.com/in')
    if c3.button("Venture Capitalist"):
        search_type = ("Venture Capitalist", '"venture capital" UAE site:linkedin.com/in')

    if search_type:
        label, query = search_type
        progress_bar = st.progress(0)
        log_area = st.empty()
        
        with DDGS() as ddgs:
            log_area.info(f"Running search for: {query}")
            search_results = list(ddgs.text(query, max_results=10))
            
            for i, r in enumerate(search_results):
                url = r.get("href", "")
                norm_url = normalize_url(url)
                
                # De-duplication check
                is_duplicate = any(normalize_url(lead['URL']) == norm_url for lead in st.session_state['all_leads'])
                if is_duplicate:
                    continue

                title = r.get("title", "")
                body = r.get("body", "")
                name = title.split("-")[0].strip()
                
                log_area.markdown(f"Processing: {name}")
                
                # 1. First Pass Scoring
                fp_score, _, fp_signals, _ = score_text(body, query, url)
                
                # 2. Second Pass Verification
                sp_score = 0.0
                if fp_score >= 4.0:
                    state = {
                        "linkedin_hits": 0, "domain_hits": set(), 
                        "identity_confirmed": False, "geo_hits": 0, 
                        "expected_name": name.lower()
                    }
                    sp_score, _, _ = second_pass.score_second_pass(body, url, state)
                
                combined_text = (title + " " + body).lower()
                total_points = fp_score + sp_score
                
                entry = {
                    "Name": name,
                    "Identity": extract_found_keywords(combined_text, identity_keywords),
                    "Seniority": extract_found_keywords(combined_text, seniority_keywords),
                    "Geography": extract_found_keywords(combined_text, uae_keywords + mena_keywords),
                    "Verdict": "GREAT" if total_points > 8 else ("GOOD" if total_points > 5 else "NOISE"),
                    "URL": url
                }
                
                st.session_state['all_leads'].append(entry)
                progress_bar.progress((i + 1) / len(search_results))
                time.sleep(0.1)

        log_area.success("Discovery Complete")

    if st.session_state['all_leads']:
        df = pd.DataFrame(st.session_state['all_leads'])

        # --- Dashboard Metrics in Styled Cards ---
        st.divider()
        m1, m2, m3 = st.columns(3)
        m1.metric("Leads Analyzed", len(df))
        
        # Qualified leads include both GREAT and GOOD
        qualified_count = len(df[df['Verdict'].isin(['GREAT', 'GOOD'])])
        m2.metric("Qualified Leads", qualified_count)
        
        m3.metric("Review Required", len(df[df['Verdict'] == 'GOOD']))

        # --- Filters ---
        show_green = st.toggle("Show Finalists Only", value=False)
        if show_green:
            df = df[df['Verdict'].isin(['GREAT', 'GOOD'])]

        # --- Final Presentation Table ---
        st.subheader("Extracted Lead Intelligence")
        
        # Removed Final Score column as requested
        st.dataframe(
            df[["Name", "Identity", "Seniority", "Geography", "Verdict"]].sort_values("Verdict"),
            use_container_width=True,
            column_config={
                "Verdict": st.column_config.TextColumn("Status")
            }
        )
