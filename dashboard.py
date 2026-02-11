import streamlit as st
import pandas as pd
import time
from ddgs import DDGS
import first_pass
import second_pass

def inject_SaaS_theme():
    st.markdown("""
        <style>
        /* Modern Header */
        .main { background-color: #F9FAFB; }
        .stMetric { background-color: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        
        /* Badge UI */
        .keyword-badge {
            background-color: #E0E7FF; color: #4338CA;
            padding: 2px 8px; border-radius: 12px;
            font-size: 0.75rem; font-weight: 600; margin: 2px;
            display: inline-block; border: 1px solid #C7D2FE;
        }
        </style>
    """, unsafe_allow_html=True)

def get_found_tags(text, keywords):
    """Checks text against keyword list and returns unique found items."""
    found = [k.upper() for k in keywords if k.lower() in text.lower()]
    return list(set(found))

def run_dashboard():
    inject_SaaS_theme()
    st.title("💎 Investor Discovery Hub")
    st.caption("AI-Powered Lead Intelligence & Verification")

    # Configuration
    with st.expander("🔍 Search Settings", expanded=True):
        col1, col2 = st.columns([3, 1])
        query = col1.text_input("Global Search Query", value='"angel investor" Dubai site:linkedin.com/in')
        limit = col2.number_input("Lead Limit", 5, 50, 10)
    
    if st.button("🚀 Start Deep Discovery"):
        results_data = []
        
        # This container makes it look like a high-end SaaS tool
        with st.status("🕵️ System Initialized: Scanning Global Sources...", expanded=True) as status:
            with DDGS() as ddgs:
                raw_hits = list(ddgs.text(query, max_results=limit))
                
                for i, hit in enumerate(raw_hits):
                    title = hit.get('title', 'Unknown')
                    url = hit.get('href', '')
                    body = hit.get('body', '')
                    name = title.split('|')[0].split('-')[0].strip()
                    
                    status.update(label=f"Analyzing Lead {i+1}/{len(raw_hits)}: {name}")
                    
                    # 1. First Pass
                    fp_score, _, fp_signals, _ = first_pass.score_text(f"{title} {body}", query, url)
                    
                    # 2. Second Pass
                    sp_score = 0.0
                    sp_signals = []
                    if fp_score > 4.0:
                        st.write(f"✨ **High Confidence match for {name}**. Running verification...")
                        # FIXED: Correct function call from second_pass.py
                        state = {"linkedin_hits": 0, "domain_hits": set(), "identity_confirmed": False, "geo_hits": 0, "expected_name": name.lower()}
                        sp_score, sp_signals, _ = second_pass.score_second_pass(f"{title} {body}", url, state)
                    
                    # 3. Consolidate Data
                    total_score = (fp_score + sp_score) / 2
                    combined_text = f"{title} {body}".lower()
                    
                    results_data.append({
                        "Name": name,
                        "Final Score": round(total_score, 1),
                        "Seniority": get_found_tags(combined_text, first_pass.seniority_keywords),
                        "Identity": get_found_tags(combined_text, first_pass.identity_keywords),
                        "Geography": get_found_tags(combined_text, first_pass.uae_keywords + first_pass.mena_keywords),
                        "Verdict": "GREAT" if total_score >= 7.5 else ("GOOD" if total_score >= 5.0 else "NOISE"),
                        "URL": url
                    })
            
            status.update(label="✅ Discovery Process Complete", state="complete", expanded=False)

        # --- Dashboard Metrics ---
        df = pd.DataFrame(results_data)
        st.divider()
        
        m1, m2, m3 = st.columns(3)
        green_count = len(df[df['Verdict'] == "GREAT"])
        m1.metric("Qualified Leads", green_count, delta=f"{green_count} High Confidence")
        m2.metric("Identity Matches", df['Identity'].apply(lambda x: len(x) > 0).sum())
        m3.metric("Geo Verified", df['Geography'].apply(lambda x: len(x) > 0).sum())

        # --- Filters & Display ---
        show_only_green = st.toggle("Show Only Green List (Finalists)")
        
        display_df = df.copy()
        if show_only_green:
            display_df = display_df[display_df['Verdict'] == "GREAT"]

        # Formatting Lists for Display
        display_df['Identity'] = display_df['Identity'].apply(lambda x: " | ".join(x) if x else "—")
        display_df['Seniority'] = display_df['Seniority'].apply(lambda x: " | ".join(x) if x else "—")
        display_df['Geography'] = display_df['Geography'].apply(lambda x: " | ".join(x) if x else "—")

        st.subheader("Final Consolidation Table")
        st.dataframe(
            display_df[["Name", "Final Score", "Identity", "Seniority", "Geography", "Verdict", "URL"]].sort_values("Final Score", ascending=False),
            use_container_width=True,
            column_config={
                "URL": st.column_config.LinkColumn("Source"),
                "Final Score": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=12)
            }
        )
