import streamlit as st
import pandas as pd
import time
import random

# Import your existing backend logic
# Ensure these files are in the same directory
from first_pass import score_text, identity_keywords, behavior_keywords, uae_keywords
from second_pass import NOISE_DOMAINS, BONUS_DOMAINS

# --- CONFIGURATION & STYLING ---
st.set_page_config(page_title="TekhLeads UAE Investor Discovery", layout="wide")

# Custom CSS for that "Premium SaaS" look
# - Hides default Streamlit menu/footer for a clean video
# - Styles the "Green List" metrics
# - Adds whitespace for breathing room
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Premium Card Metric Styling */
    div[data-testid="stMetric"] {
        background-color: #f9f9f9;
        border: 1px solid #e0e0e0;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    /* Custom Button Styling */
    div.stButton > button {
        width: 100%;
        background-color: #0068C9;
        color: white;
        font-weight: bold;
        border-radius: 8px;
        height: 50px;
    }
</style>
""", unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---

def fake_stream_output(text):
    """Simulates a typewriter effect for the 'AI thinking' look in the demo."""
    for word in text.split():
        yield word + " "
        time.sleep(0.05)

def clean_dataframe_for_display(df):
    """Prepares the raw data for the sleek UI."""
    if df.empty:
        return df
    
    display_df = df.copy()
    
    # 1. Rename columns for display
    display_df = display_df.rename(columns={
        "Name": "Name",
        "Enriched Company": "Affiliation",
        "Final Score": "Trust Score",
        "Final Verdict": "Status"
    })
    
    # 2. Add a 'Profile' column that is just the URL (Streamlit will format this)
    if "Source" in display_df.columns:
        display_df["LinkedIn"] = display_df["Source"]
    elif "URL" in display_df.columns:
        display_df["LinkedIn"] = display_df["URL"]
        
    # 3. Create a clean 'Signals' column
    # Combine identity/geo/behavior into one readable tag string
    def combine_signals(row):
        signals = []
        # We need to safely check if these columns exist or parse them from breakdown
        # For this demo, we assume they might be in the 'Breakdown' or separate cols
        # This is a simplified logic for the visual demo
        score = row.get("Trust Score", 0)
        if score > 8: signals.append("High Potential")
        if "UAE" in str(row): signals.append("United Arab Emirates")
        if "angel" in str(row).lower(): signals.append("Angel Investor")
        return ", ".join(signals)

    display_df["Signals"] = display_df.apply(combine_signals, axis=1)

    # 4. Filter to only show relevant columns
    cols_to_show = ["Name", "Affiliation", "Trust Score", "Status", "Signals", "LinkedIn"]
    # Only keep columns that actually exist
    final_cols = [c for c in cols_to_show if c in display_df.columns]
    
    return display_df[final_cols]

# --- MAIN APP FLOW ---

def run_dashboard():
    # Title Section
    st.title("TekhLeads UAE Investor Discovery")
    st.caption("AI-Powered Lead Intelligence for finding high-potential leads")

    st.markdown("---")

    # 1. INPUT SECTION
    with st.container():
        col_search, col_btn = st.columns([4, 1])
        
        with col_search:
            # Pre-filled for the demo video smoothness
            query = st.text_input(
                "Target Persona", 
                value="Real Estate Investors", 
                placeholder="e.g. Fintech Angels, Family Offices..."
            )
        
        with col_btn:
            st.write("") # Spacer
            st.write("") # Spacer
            run_btn = st.button("Find Leads")

    # Initialize State
    if "leads" not in st.session_state:
        st.session_state.leads = pd.DataFrame()
    if "is_searching" not in st.session_state:
        st.session_state.is_searching = False

    # 2. EXECUTION LOGIC
    if run_btn:
        st.session_state.is_searching = True
        
        # VISUAL: Progress Status
        with st.status("AI Agent Active", expanded=True) as status:
            
            # Step 1: First Pass
            st.write("Running Search...")
            # In a real demo, we might want to simulate a slight delay so viewers can read
            time.sleep(1.0) 
            
            # --- HOOK INTO YOUR EXISTING CODE HERE ---
            # Ideally, import `first_pass_search` from your main file or replicate logic
            # For this standalone file, I will simulate the structure based on your description
            # REPLACE THIS WITH ACTUAL FUNCTION CALL: 
            # results_fp = first_pass.run_search(query + " uae", num_results=10)
            
            # *Simulating* data for the perfect demo video if backend is unstable
            # Remove this block and uncomment above when ready
            st.write("Identifying high-potential candidates...")
            time.sleep(1.0)
            
            st.write("• Verifying geography and investor relevance...")
            time.sleep(1.0)
            
            status.update(label="Discovery Complete", state="complete", expanded=False)

        # 3. CONSOLIDATION (Simulated for Demo Visuals - Replace with your `df_consolidated` logic)
        # This ensures your video looks perfect even if the live DDGS search hits a rate limit
        data = [
            {"Name": "Khalid Al-Mansoori", "Enriched Company": "Emaar Properties / Private Office", "Final Score": 9.2, "Final Verdict": "GREEN LIST", "URL": "https://linkedin.com/in/example1", "Text": "Angel investor based in Dubai UAE"},
            {"Name": "Sarah Johnson", "Enriched Company": "Global Ventures", "Final Score": 8.5, "Final Verdict": "GREEN LIST", "URL": "https://linkedin.com/in/example2", "Text": "Partner at VC fund, investing in MENA"},
            {"Name": "Rajiv Mehta", "Enriched Company": "Sobha Realty", "Final Score": 7.8, "Final Verdict": "GREEN LIST", "URL": "https://linkedin.com/in/example3", "Text": "Director, active investor in proptech"},
            {"Name": "Amira Youssef", "Enriched Company": "Unknown", "Final Score": 4.2, "Final Verdict": "RED LIST", "URL": "https://linkedin.com/in/example4", "Text": "Student at University of Dubai"},
            {"Name": "James Wright", "Enriched Company": "Consultant", "Final Score": 3.5, "Final Verdict": "RED LIST", "URL": "https://linkedin.com/in/example5", "Text": "Looking for investment opportunities"},
        ]
        st.session_state.leads = pd.DataFrame(data)

    # 4. RESULTS DISPLAY
    if not st.session_state.leads.empty:
        df = st.session_state.leads
        
        # Top Level Metrics
        m1, m2, m3 = st.columns(3)
        green_list_count = len(df[df["Final Verdict"] == "GREEN LIST"])
        avg_score = df["Final Score"].mean()
        
        m1.metric("Total Candidates", len(df))
        m2.metric("Green List Leads", green_list_count, delta="High Quality")
        m3.metric("Avg Trust Score", f"{avg_score:.1f}/10")
        
        st.divider()
        
        st.subheader("Verified Candidates")
        
        # Filter Toggle
        show_green_only = st.toggle("Show Green List Only", value=True)
        
        display_df = clean_dataframe_for_display(df)
        
        if show_green_only:
            display_df = display_df[display_df["Status"] == "GREEN LIST"]
        
        # THE PREMIUM TABLE CONFIGURATION
        st.dataframe(
            display_df,
            use_container_width=True,
            column_config={
                "LinkedIn": st.column_config.LinkColumn(
                    "LinkedIn Profile",
                    display_text="View Profile",
                    help="Click to open LinkedIn Profile"
                ),
                "Trust Score": st.column_config.ProgressColumn(
                    "AI Confidence",
                    format="%.1f",
                    min_value=0,
                    max_value=10,
                ),
                "Status": st.column_config.Column(
                    "Verdict",
                    width="medium",
                ),
                "Affiliation": st.column_config.TextColumn(
                    "Affiliation",
                    width="large"
                )
            },
            hide_index=True
        )
        
        # Load More / Download Actions
        col_load, col_dl = st.columns([1, 4])
        with col_load:
            if st.button("Load More"):
                with st.spinner("Searching..."):
                    time.sleep(2)
                    st.toast("Rate limit reached on demo tier.", icon="⚠️")
        with col_dl:
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                "Export Excel",
                data=csv,
                file_name="investor_leads.csv",
                mime="text/csv",
            )

if __name__ == "__main__":
    run_dashboard()
