import streamlit as st
from ddgs import DDGS
import pandas as pd
import time
import re

# --- DIRECT IMPORTS (KEEPING NAMES EXACT) ---
from first_pass import score_text, identity_keywords, behavior_keywords, uae_keywords, mena_keywords
import second_pass 

# --- HELPER FUNCTIONS FROM STREAMLIT_APP2.PY (ZERO CHANGES) ---
def normalize_url(url):
    return url.split("?")[0].lower().strip()

def extract_name(title):
    # Standard LinkedIn title cleaning
    name = title.split("|")[0].split("-")[0].split("—")[0].strip()
    return name

def soft_truncate_ellipsis(text: str) -> str:
    if not text: return text
    if "..." in text: return text.split("...")[0].strip()
    return text

def is_valid_name(name):
    # Logic to filter out noise titles
    blacklist = ["linkedin", "angel investor", "top", "best", "investment", "directory", "profiles", "investors"]
    if not name or len(name) < 3:
        return False
    if any(word in name.lower() for word in blacklist):
        return False
    return True

def extract_keywords_from_breakdown(breakdown_list):
    """
    Extracts actual keywords from the first_pass breakdown list 
    to show as tags in the UI.
    """
    tags = []
    # Keywords to look for in the breakdown strings
    look_for = identity_keywords + behavior_keywords + uae_keywords + mena_keywords
    for entry in breakdown_list:
        entry_lower = entry.lower()
        for k in look_for:
            if k in entry_lower:
                tags.append(k.title())
    return list(dict.fromkeys(tags))[:6] # Unique tags only

# --- STYLING ---
st.markdown("""
<style>
    .investor-card {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    .investor-name {
        font-size: 26px;
        font-weight: 800;
        color: #111827;
        margin-bottom: 4px;
    }
    .company-name {
        font-size: 18px;
        color: #4b5563;
        margin-bottom: 16px;
    }
    .signal-tag {
        display: inline-block;
        background-color: #eff6ff;
        color: #1d4ed8;
        padding: 4px 12px;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 600;
        margin-right: 8px;
        margin-bottom: 8px;
        border: 1px solid #dbeafe;
    }
    .verdict-badge {
        float: right;
        padding: 6px 16px;
        border-radius: 50px;
        font-size: 14px;
        font-weight: 700;
        text-transform: uppercase;
    }
    .green-list { background-color: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
    .red-list { background-color: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
    
    .linkedin-link {
        display: inline-block;
        margin-top: 15px;
        color: #0077b5;
        text-decoration: none;
        font-weight: 600;
        font-size: 15px;
    }
</style>
""", unsafe_allow_html=True)

# --- DASHBOARD UI ---

def run_dashboard():
    # Header logic from dashboard12.py
    st.title("TekhLeads UAE Investor Discovery")
    st.markdown("Automated intelligence for identifying high-net-worth individuals in the UAE region.")
    
    if "db_results" not in st.session_state:
        st.session_state.db_results = []
    if "processed_urls" not in st.session_state:
        st.session_state.processed_urls = set()

    st.divider()

    # 1. THE ONE ACTION BUTTON (PROS: Clean for video, CONS: Less granular control)
    c1, c2, c3 = st.columns([1.5, 1, 1])
    with c1:
        launch_discovery = st.button("🚀 Start Discovery Agent", use_container_width=True, type="primary")
    with c2:
        # High-value toggle
        show_only_green = st.toggle("Green List Only", value=True)
    with c3:
        # Load More button (PROS: Shows growth, CONS: Can trigger rate limits)
        load_more = st.button("➕ Find More Leads", use_container_width=True)

    # 2. THE SEARCH LOOP (LITERAL BACKEND FROM STREAMLIT_APP2.PY)
    if launch_discovery or load_more:
        if launch_discovery:
            st.session_state.db_results = []
            st.session_state.processed_urls = set()

        query = '"angel investor" UAE site:linkedin.com/in'
        
        with st.status("🔍 Discovery Agent Running...", expanded=True) as status:
            try:
                with DDGS() as ddgs:
                    # Fetching slightly more results to ensure quality after noise removal
                    results = list(ddgs.text(query, max_results=15, backend="lite"))
                    
                    for r in results:
                        url = normalize_url(r.get("href", ""))
                        if url in st.session_state.processed_urls: continue
                        st.session_state.processed_urls.add(url)
                        
                        title = soft_truncate_ellipsis(r.get("title", ""))
                        snippet = soft_truncate_ellipsis(r.get("body", ""))
                        name = extract_name(title)
                        
                        # Apply noise filtering helper
                        if not is_valid_name(name): continue
                        
                        status.write(f"Analyzing: **{name}**")
                        
                        # First Pass Scoring
                        score1, conf, breakdown, enriched_comp = score_text(f"{title} {snippet}", query, url)
                        
                        # Second Pass Verification
                        status.write(f"↳ Verifying credentials for {name}...")
                        anchors = second_pass.extract_anchors(snippet)
                        queries = second_pass.build_second_pass_queries(name, anchors, enriched_comp)
                        
                        sp_score = 0
                        sp_breakdown = []
                        if queries:
                            time.sleep(0.4) # Ethical delay
                            try:
                                v_res = list(ddgs.text(queries[0], max_results=3, backend="lite"))
                                state = {"linkedin_seen":False, "geo_hits":0, "identity_confirmed":False, 
                                         "domain_hits":set(), "expected_name":name.lower(), "linkedin_hits":0}
                                for vr in v_res:
                                    v_text = f"{vr.get('title','')} {vr.get('body','')}"
                                    s2, b2, _ = second_pass.score_second_pass(v_text, vr.get("href",""), state)
                                    sp_score += s2
                                    sp_breakdown.extend(b2)
                            except: pass

                        # Consolidation
                        final_score = round((score1 + min(sp_score, 10)) / 2, 1)
                        verdict = "Green List" if final_score >= 5.0 else "Red List"
                        
                        # Extract real keywords for signals
                        all_signals = extract_keywords_from_breakdown(breakdown + sp_breakdown)
                        
                        st.session_state.db_results.append({
                            "Name": name,
                            "Score": final_score,
                            "Verdict": verdict,
                            "Company": enriched_comp if enriched_comp else "Private Office / Angel",
                            "Signals": all_signals,
                            "URL": url,
                            "Snippet": snippet
                        })
                
                status.update(label="Analysis Complete", state="complete", expanded=False)
            except Exception as e:
                st.error(f"Search error: {e}")

    # 3. DISPLAY RESULTS (PREMIUM CARDS)
    if st.session_state.db_results:
        df = pd.DataFrame(st.session_state.db_results)
        
        # Metrics using "Discovery Yield" instead of Avg Score
        m1, m2, m3 = st.columns(3)
        total = len(df)
        green_count = len(df[df["Verdict"] == "Green List"])
        yield_pct = int((green_count / total) * 100) if total > 0 else 0
        
        m1.metric("Investors Found", total)
        m2.metric("Verified Green List", green_count)
        m3.metric("Discovery Yield", f"{yield_pct}%")

        st.divider()

        # Render Cards
        display_df = df[df["Verdict"] == "Green List"] if show_only_green else df
        display_df = display_df.sort_values(by="Score", ascending=False)

        for _, row in display_df.iterrows():
            verdict_class = "green-list" if row['Verdict'] == "Green List" else "red-list"
            
            tags_html = "".join([f'<span class="signal-tag">{tag}</span>' for tag in row['Signals']])
            
            card_html = f"""
            <div class="investor-card">
                <span class="verdict-badge {verdict_class}">{row['Verdict']}</span>
                <div class="investor-name">{row['Name']}</div>
                <div class="company-name">🏢 {row['Company']}</div>
                <div style="margin-top: 10px;">
                    {tags_html}
                </div>
                <div style="margin-top: 15px; font-size: 14px; color: #6b7280; font-style: italic;">
                    "{row['Snippet'][:120]}..."
                </div>
                <div style="margin-top: 20px; border-top: 1px solid #f3f4f6; padding-top: 10px;">
                    <span style="font-weight: 700; color: #374151;">AI Confidence Score: {row['Score']}/10</span>
                </div>
                <a href="{row['URL']}" target="_blank" class="linkedin-link">View Full Profile ↗</a>
            </div>
            """
            st.markdown(card_html, unsafe_allow_html=True)

        # Download button from dashboard12.py
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            "Export Excel", # Keeping name from your file
            data=csv,
            file_name="uae_investor_leads.csv",
            mime="text/csv",
        )

if __name__ == "__main__":
    run_dashboard()
