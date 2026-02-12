import streamlit as st
from ddgs import DDGS
import pandas as pd
import time
import re

# --- STRICT IMPORTS FROM YOUR BACKEND ---
# We use your exact logic to ensure authentic results
from first_pass import score_text, identity_keywords, behavior_keywords, uae_keywords, mena_keywords
import second_pass 

# --- CONFIGURATION & CSS ---
st.set_page_config(page_title="TekhLeads | Investor Intelligence", layout="wide", page_icon="💎")

st.markdown("""
<style>
    /* HIDE STREAMLIT CHROME */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* CARD STYLING */
    .investor-card {
        background-color: white;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #f0f2f6;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        margin-bottom: 20px;
        transition: transform 0.2s;
    }
    .investor-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0,0,0,0.1);
        border-color: #0068C9;
    }
    
    /* TYPOGRAPHY */
    .card-name {
        font-size: 22px;
        font-weight: 700;
        color: #1f2937;
        margin-bottom: 5px;
    }
    .card-role {
        font-size: 16px;
        color: #6b7280;
        margin-bottom: 12px;
    }
    
    /* BADGES & TAGS */
    .score-badge-green {
        background-color: #d1fae5;
        color: #065f46;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 14px;
        float: right;
    }
    .score-badge-red {
        background-color: #fee2e2;
        color: #991b1b;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 14px;
        float: right;
    }
    .tag-pill {
        display: inline-block;
        background-color: #f3f4f6;
        color: #374151;
        padding: 2px 10px;
        border-radius: 6px;
        font-size: 12px;
        margin-right: 6px;
        margin-top: 6px;
    }
    
    /* LINK BUTTON */
    .linkedin-btn {
        display: inline-block;
        text-decoration: none;
        color: #0077b5;
        font-weight: 600;
        font-size: 14px;
        margin-top: 15px;
    }
    .linkedin-btn:hover {
        text-decoration: underline;
    }
    
    /* METRICS CONTAINER */
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e5e7eb;
        padding: 20px;
        border-radius: 10px;
    }
</style>
""", unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---

def normalize_url(url):
    return url.split("?")[0].lower().strip()

def clean_signal_text(signal_list_str):
    """
    Parses the raw 'Signals' string from first_pass.py (e.g., '#uae = geography (+0.6)')
    into clean, readable tags for the UI.
    """
    if not isinstance(signal_list_str, str):
        return []
    
    raw_signals = signal_list_str.split(" | ")
    clean_tags = []
    
    for s in raw_signals:
        # Remove the score part like (+0.6)
        s_base = s.split("(")[0].strip()
        # Remove hash and grouping info like '#uae = geography'
        if "=" in s_base:
            # Take the part before '=', remove #
            tag_name = s_base.split("=")[0].replace("#", "").strip()
        else:
            tag_name = s_base
            
        # Capitalize
        clean_tags.append(tag_name.title())
        
    # Deduplicate and limit to 4 tags for UI cleanliness
    return list(dict.fromkeys(clean_tags))[:5]

def render_lead_card(lead):
    """
    Renders a single lead as a beautiful HTML card.
    """
    score = lead.get("Final Score", 0)
    is_green = lead.get("Final Verdict") == "GREAT" or lead.get("Final Verdict") == "GOOD"
    badge_class = "score-badge-green" if is_green else "score-badge-red"
    verdict_text = "Highly Recommended" if is_green else "Review Needed"
    
    # Clean up signals
    signals = clean_signal_text(lead.get("Signals", ""))
    tags_html = "".join([f'<span class="tag-pill">{tag}</span>' for tag in signals])
    
    # Company Display
    company = lead.get("Enriched Company")
    if not company:
        company = "Private Investor / Undisclosed"
    
    # Card HTML
    html = f"""
    <div class="investor-card">
        <span class="{badge_class}">{score}/10</span>
        <div class="card-name">{lead['Name']}</div>
        <div class="card-role">🏢 {company}</div>
        <div style="margin-bottom:10px;">
            {tags_html}
        </div>
        <div style="font-size:13px; color:#9ca3af; margin-top:8px; font-style:italic;">
            "{lead.get('Snippet', '')[:90]}..."
        </div>
        <a href="{lead.get('URL', '#')}" target="_blank" class="linkedin-btn">
            View LinkedIn Profile ↗
        </a>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# --- CORE LOGIC ---

def run_dashboard():
    # Header
    c1, c2 = st.columns([3, 1])
    with c1:
        st.title("TekhLeads | Investor Discovery")
        st.caption("Auto-Agent: Target Region **UAE** • Strategy **Angel Investors**")
    
    # Initialize Session State
    if "db_leads" not in st.session_state:
        st.session_state.db_leads = []
    if "db_processed_urls" not in st.session_state:
        st.session_state.db_processed_urls = set()

    st.markdown("---")

    # 1. CONTROL PANEL
    with st.container():
        # Using columns to center or align buttons
        col_act, col_filter = st.columns([1, 4])
        
        with col_act:
            # THE ONE BUTTON
            start_btn = st.button("🚀 Launch AI Agent", type="primary")
            
        with col_filter:
            # A toggle to filter results instantly
            show_green_only = st.toggle("Show Green List Candidates Only", value=True)

    # 2. LIVE PROCESSING LOOP
    if start_btn:
        st.session_state.db_leads = [] # Clear previous run for the demo
        
        # We use a progress container to show the "AI Thinking"
        status_container = st.status("Initializing Agent...", expanded=True)
        
        try:
            # STEP A: PUBLIC DISCOVERY (First Pass)
            status_container.write("📡 Scanning public directories (LinkedIn UAE)...")
            
            # HARDCODED QUERY as requested
            query = '"angel investor" UAE site:linkedin.com/in'
            
            # Run DDGS (Live Data)
            # We run a loop to get enough candidates
            found_candidates = []
            
            with DDGS() as ddgs:
                # Fetching 15 results to ensure we get some hits
                results = list(ddgs.text(query, max_results=15, backend="lite"))
                
                status_container.write(f"✓ Found {len(results)} raw profiles. Analyzing signals...")
                progress_bar = status_container.progress(0)
                
                for idx, r in enumerate(results):
                    url = r.get("href", "")
                    if not url: continue
                    
                    # Deduplication
                    norm_url = normalize_url(url)
                    if norm_url in st.session_state.db_processed_urls:
                        continue
                    st.session_state.db_processed_urls.add(norm_url)

                    # Scoring (First Pass)
                    title = r.get("title", "")
                    snippet = r.get("body", "")
                    text_blob = f"{title} {snippet}"
                    
                    score1, conf, breakdown, enriched_comp = score_text(text_blob, query, url)
                    
                    # Filter: Only proceed if it looks somewhat promising (Score > 3)
                    if score1 >= 3.0:
                        candidate = {
                            "Name": title.split("|")[0].split("-")[0].strip(), # Simple name clean
                            "URL": url,
                            "Snippet": snippet,
                            "Score1": score1,
                            "Enriched Company": enriched_comp,
                            "Signals": " | ".join(breakdown),
                            "Title": title
                        }
                        found_candidates.append(candidate)
                    
                    # Update Progress
                    progress_bar.progress((idx + 1) / len(results))
                    time.sleep(0.1) # Tiny sleep for visual smoothness in video

            # STEP B: VERIFICATION (Second Pass)
            if found_candidates:
                status_container.write(f"🕵️ Verifying {len(found_candidates)} candidates...")
                
                final_results = []
                
                for i, cand in enumerate(found_candidates):
                    # Show who we are verifying currently
                    status_container.update(label=f"Verifying: {cand['Name']}...", state="running")
                    
                    # 1. Build Verification Query
                    # We use the logic from second_pass.py (imports)
                    anchors = second_pass.extract_anchors(cand["Snippet"])
                    queries = second_pass.build_second_pass_queries(cand["Name"], anchors, cand["Enriched Company"])
                    
                    # 2. Run Verification Search (Just 1 query per person for speed in demo)
                    sp_score = 0
                    sp_breakdown = []
                    
                    if queries:
                        # Safety delay for DDGS
                        time.sleep(0.5) 
                        try:
                            v_results = list(ddgs.text(queries[0], max_results=3, backend="lite"))
                            
                            # State object required by second_pass.score_second_pass
                            state = {
                                "linkedin_seen": False, "geo_hits": 0,
                                "identity_confirmed": False, "domain_hits": set(),
                                "expected_name": cand["Name"].lower(), "linkedin_hits": 0
                            }
                            
                            for vr in v_results:
                                v_text = f"{vr.get('title','')} {vr.get('body','')}"
                                s2, b2, _ = second_pass.score_second_pass(v_text, vr.get("href",""), state)
                                if s2 > 0:
                                    sp_score += s2
                                    sp_breakdown.extend(b2)
                        except:
                            pass # Fail gracefully on connection error
                            
                    # 3. Consolidation Logic
                    final_score = (cand["Score1"] + min(sp_score, 10)) / 2
                    
                    # Verdict
                    if final_score >= 8.0: verdict = "GREAT"
                    elif final_score >= 5.0: verdict = "GOOD"
                    else: verdict = "REJECT"
                    
                    # Update Signals
                    all_signals = cand["Signals"]
                    if sp_breakdown:
                        all_signals += " | " + " | ".join(sp_breakdown)

                    final_results.append({
                        "Name": cand["Name"],
                        "Enriched Company": cand["Enriched Company"],
                        "Final Score": round(final_score, 1),
                        "Final Verdict": verdict,
                        "URL": cand["URL"],
                        "Signals": all_signals,
                        "Snippet": cand["Snippet"]
                    })
                
                # Save to session
                st.session_state.db_leads = final_results
                status_container.update(label="Discovery Complete", state="complete", expanded=False)
            else:
                status_container.error("No candidates found. Try again later.")
                
        except Exception as e:
            status_container.error(f"Search interrupted: {e}")

    # 3. RESULTS DISPLAY (The Premium Cards)
    
    if st.session_state.db_leads:
        df = pd.DataFrame(st.session_state.db_leads)
        
        # METRICS ROW
        m1, m2, m3 = st.columns(3)
        
        green_leads = df[(df["Final Verdict"] == "GREAT") | (df["Final Verdict"] == "GOOD")]
        count_total = len(df)
        count_green = len(green_leads)
        yield_rate = int((count_green / count_total) * 100) if count_total > 0 else 0
        
        m1.metric("Total Profiles Analyzed", count_total)
        m2.metric("Green List Leads", count_green)
        m3.metric("High Value Yield", f"{yield_rate}%")
        
        st.divider()
        
        # FILTERING
        leads_to_show = green_leads if show_green_only else df
        leads_to_show = leads_to_show.sort_values(by="Final Score", ascending=False)

        if leads_to_show.empty:
            st.info("No leads met the criteria.")
        else:
            # RENDER CARDS
            # We use a 2-column grid layout for the cards
            grid_cols = st.columns(2)
            
            for index, row in leads_to_show.iterrows():
                # Alternate columns
                with grid_cols[index % 2]:
                    render_lead_card(row)
        
        # FOOTER ACTIONS
        st.divider()
        c_dl, c_more = st.columns([1, 4])
        with c_dl:
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Download CSV",
                data=csv,
                file_name="investor_leads_uae.csv",
                mime="text/csv"
            )

if __name__ == "__main__":
    run_dashboard()
