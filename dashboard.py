import streamlit as st
from ddgs import DDGS
import pandas as pd
import re
import time
import random

from first_pass import (score_text, identity_keywords, behavior_keywords, uae_keywords, mena_keywords, seniority_keywords)
import second_pass

# Demo mode will be checked inside the function
# Import mock leads here so they're always available
try:
    from mock_leads import MOCK_LEADS_BATCH_1, MOCK_LEADS_BATCH_2
    MOCK_LEADS_AVAILABLE = True
except ImportError:
    MOCK_LEADS_AVAILABLE = False
    MOCK_LEADS_BATCH_1 = []
    MOCK_LEADS_BATCH_2 = []


def run_dashboard():
    """
    Premium UAE Investor Discovery Dashboard
    Clean, card-based layout with live progress tracking
    """
    
    # Set page to wide mode
    st.set_page_config(layout="wide")
    
    # ==================== CUSTOM CSS FOR PREMIUM STYLING ====================
    st.markdown("""
    <style>
    /* Main container spacing */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1200px;
    }
                
    /* Metric cards styling */
    [data-testid="stMetricValue"] {
        font-size: 1.75rem;
        font-weight: 600;
        color: #1F2937;
    }

    [data-testid="stMetricLabel"] {
        font-size: 0.85rem;
        font-weight: 500;
        color: #6B7280;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    /* Card container with shadow and border */
    .investor-card {
        background: white;
        border: 2px solid #E5E7EB;
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        transition: all 0.3s ease;
    }
    
    .investor-card:hover {
        border-color: #2563EB;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
    }
    
    /* Name styling */
    .investor-name {
        font-size: 1.5rem;
        font-weight: 700;
        color: #111827;
        margin-bottom: 8px;
    }
    
    /* Company styling */
    .investor-company {
        font-size: 1rem;
        color: #6B7280;
        margin-bottom: 16px;
        font-weight: 500;
    }
    
    /* Badge styling */
    .badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
        margin-right: 8px;
        margin-bottom: 8px;
        backdrop-filter: blur(4px);
    }
                
    .badge:hover {
        transform: scale(1.05);
        transition: transform 0.2s ease;
        cursor: default;
    }            
    
    .badge-identity {
        background-color: #DBEAFE;
        color: #1E40AF;
        border: 1px solid #93C5FD;
    }
    
    .badge-geo {
        background-color: #FEF3C7;
        color: #92400E;
        border: 1px solid #FCD34D;
    }
    
    .badge-seniority {
        background-color: #DBEAFE;
        color: #1E40AF;
        border: 1px solid #93C5FD;
    }
    
    .badge-green {
        background-color: #D1FAE5;
        color: #065F46;
        border: 2px solid #10B981;
        font-size: 0.9rem;
        padding: 6px 14px;
    }
    
    .badge-red {
        background-color: #FEE2E2;
        color: #991B1B;
        border: 2px solid #EF4444;
        font-size: 0.9rem;
        padding: 6px 14px;
    }
    
    /* Button styling */
    .stButton > button {
        width: 100%;
        background-color: #2563EB;
        color: white;
        border: none;
        padding: 12px 24px;
        font-size: 1rem;
        font-weight: 600;
        border-radius: 8px;
        box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.3);
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        background-color: #1D4ED8;
        box-shadow: 0 10px 15px -3px rgba(37, 99, 235, 0.4);
        transform: translateY(-2px);
    }
    
    /* LinkedIn link button */
    .linkedin-btn {
        display: inline-block;
        background-color: #0A66C2;
        color: white;
        padding: 8px 16px;
        border-radius: 6px;
        text-decoration: none;
        font-weight: 600;
        font-size: 0.9rem;
        transition: all 0.3s ease;
    }
    
    .linkedin-btn:hover {
        background-color: #004182;
        text-decoration: none;
        color: white;
    }
    
    /* Progress container */
    .progress-container {
        background: #F9FAFB;
        border: 2px solid #E5E7EB;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 20px;
    }
    
    /* Download button */
    .stDownloadButton > button {
        width: 100%;
        background-color: #10B981;
        color: white;
        border: none;
        padding: 12px 24px;
        font-size: 1rem;
        font-weight: 600;
        border-radius: 8px;
        box-shadow: 0 4px 6px -1px rgba(16, 185, 129, 0.3);
    }
    
    .stDownloadButton > button:hover {
        background-color: #059669;
    }
    
    /* Bring progress bar very close to card */
    div[data-testid="stProgress"] {
        margin-top: -8px !important;
        margin-bottom: 20px !important;
    }
    
    /* CSS-only progress bar inside card */
    .progress-container {
        margin-top: 12px;
        padding-top: 12px;
        border-top: 1px solid #E5E7EB;
    }

    .progress-label {
        font-size: 0.85rem;
        color: #6B7280;
        margin-bottom: 6px;
        font-weight: 500;
    }

    .progress-bar-bg {
        width: 100%;
        height: 8px;
        background-color: #E5E7EB;
        border-radius: 10px;
        overflow: hidden;
    }

    .progress-bar-fill {
        height: 100%;
        background: linear-gradient(90deg, #3B82F6, #2563EB);
        border-radius: 10px;
        transition: width 0.3s ease;
    }

/* Checkbox styling */            
    /* Checkbox styling */
    .stCheckbox {
        font-size: 1rem;
        font-weight: 500;
    }
    
    /* Divider spacing */
    hr {
        margin: 2rem 0;
        border: none;
        border-top: 2px solid #E5E7EB;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # ==================== HEADER ====================
    st.markdown(
        "<h1 style='text-align: center; font-size: 2.25rem; margin-bottom: 0.5rem;'>"
        "TekhLeads UAE Investor Discovery Platform"
        "</h1>", 
        unsafe_allow_html=True
    )
    st.markdown(
        "<h3 style='text-align: center; color: #6B7280; font-size: 1.1rem; font-weight: 400; margin-top: 0;'>"
        "AI-Driven Lead Intelligence for High-Value Investors"
        "</h3>", 
        unsafe_allow_html=True
    )    
    st.markdown("---")
    
    # ==================== SESSION STATE INITIALIZATION ====================
    if "dashboard_results" not in st.session_state:
        st.session_state.dashboard_results = []
    if "dashboard_verified" not in st.session_state:
        st.session_state.dashboard_verified = []
    if "trigger_discovery" not in st.session_state:
        st.session_state.trigger_discovery = False
    if "first_discovery_done" not in st.session_state:
        st.session_state.first_discovery_done = False
    if "demo_batch_index" not in st.session_state:
        st.session_state.demo_batch_index = 0  # Track which batch to use (0=batch1, 1=batch2)    
    
    # ==================== HELPER FUNCTIONS ====================
    blocked_urls = [
        "bing.com/aclick",
        "bing.com/ck/a",
        "doubleclick.net"
    ]
    
    def normalize_url(url):
        return url.split("?")[0].lower().strip()
    
    def soft_truncate_ellipsis(text: str) -> str:
        if not text: return text
        if "..." in text: return text.split("...")[0].strip()
        return text
    
    def is_duplicate_url(url, existing_results, title, snippet):
        norm = normalize_url(url)
        for r in existing_results:
            if normalize_url(r.get("URL", "")) == norm:
                old_text = (r.get("Title","") + r.get("Snippet","")).lower()
                new_text = (title + snippet).lower()
                if len(set(new_text.split()) - set(old_text.split())) < 5:
                    return True
        return False
    
    def find_existing_person(url, existing_results):
        norm = normalize_url(url)
        for i, r in enumerate(existing_results):
            if normalize_url(r.get("URL", "")) == norm:
                return i
        return None
    
    def is_valid_person_name(name):
        if not name: return False
        if len(name.split()) < 2: return False
        if re.fullmatch(r"[A-Z][a-z]+\s*\.", name): return False
        if name.lower() in {"angel investor", "venture capital"}: return False
        return True
    
    def extract_name(title):
        for sep in [" - ", " | ", " – ", " — "]:
            if sep in title:
                return title.split(sep)[0].strip()
        return title.strip()
    
    def extract_keywords_from_signals(signals_text, keyword_list):
        """Extract exact keywords found from signal breakdown"""
        found = []
        signals_lower = signals_text.lower()
        for kw in keyword_list:
            if kw in signals_lower:
                found.append(kw)
        
        # Remove "angel" if "angel investor" is present
        if "angel investor" in found and "angel" in found:
            found.remove("angel")

        if "advisor" in found and "advisory" in found:
            found.remove("advisory")
        
        return list(set(found))
    
    def format_badge_text(keyword):
        """Format keyword for badge display, keeping acronyms uppercase"""
        acronyms = ["ceo", "cio", "cfo", "cto", "coo", "vp", "uae", "gcc", "mena", "ai", "usa", "uk"]
        keyword_lower = keyword.lower()
        
        if keyword_lower in acronyms:
            return keyword.upper()
        else:
            return keyword.title()
    
    # ==================== METRICS SECTION ====================
    col1, col2, col3, col4 = st.columns(4)

    total_discovered = len(st.session_state.dashboard_results)

    # Fix: Count unique verified names, not total verification records
    verified_names = set()
    if st.session_state.dashboard_verified:
        df_verified = pd.DataFrame(st.session_state.dashboard_verified)
        verified_names = set(df_verified["Name"].unique())
    verified_count = len(verified_names)

    # UAE-Connected: Count leads with UAE keywords
    uae_connected_count = sum(
        1 for r in st.session_state.dashboard_results 
        if r.get("Geo Keywords") and len(r.get("Geo Keywords", [])) > 0
    )

    # High-Value: Count leads with score >= 7
    high_value_count = sum(
        1 for r in st.session_state.dashboard_results 
        if r.get("Score", 0) >= 7.0
    )

    green_list_count = sum(1 for r in st.session_state.dashboard_results 
                        if r.get("Final Verdict") == "Green List")

    with col1:
        st.metric(
            label="Total Discovered",
            value=total_discovered,
            delta=None
        )

    with col2:
        st.metric(
            label="Verified Investors",
            value=verified_count,
            delta=None
        )

    with col3:
        st.metric(
            label="Based in the UAE",
            value=uae_connected_count,
            delta=None
        )

    with col4:
        st.metric(
            label="High-Value Leads",
            value=high_value_count,
            delta=None
        )
    
    st.markdown("---")
    
    # ==================== DISCOVER BUTTON ====================
    if not st.session_state.first_discovery_done:
        # Show initial discovery button
        col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
        with col_btn2:
            discover_button = st.button("Discover UAE Investors", use_container_width=True, type="primary")
        
        should_discover = discover_button
    else:
        # After first discovery, show info message with reset option
        col_info1, col_info2, col_info3 = st.columns([1, 2, 1])
        with col_info2:
            st.info("Scroll down and use 'Discover More' to find additional leads.")
            if st.button("Reset Search", use_container_width=True, key="reset_search"):
                st.session_state.first_discovery_done = False
                st.session_state.dashboard_results = []
                st.session_state.dashboard_verified = []
                st.rerun()
        
        should_discover = False
    
    # Check if discovery should run via trigger from "Discover More" button
    if st.session_state.trigger_discovery:
        should_discover = True
        st.session_state.trigger_discovery = False
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # ==================== DISCOVERY PROCESS ====================
    if should_discover:
        # Set flag that first discovery has been completed
        st.session_state.first_discovery_done = True
        
        # Check demo mode from session state (inside function where it exists)
        demo_mode_active = st.session_state.get("demo_mode", False)
        
        # ==================== DEMO MODE BRANCH ====================
        if demo_mode_active:
            # Safety check - ensure mock leads are available
            if not MOCK_LEADS_AVAILABLE or not MOCK_LEADS_BATCH_1:
                st.error("❌ Mock leads not found! Make sure mock_leads.py is in the same folder.")
                st.stop()
            # Use mock data instead of DDGS
            query = '"angel investor" UAE site:linkedin.com/in'
            
            # Select which batch to use
            if st.session_state.demo_batch_index == 0:
                mock_leads_to_use = MOCK_LEADS_BATCH_1
            else:
                mock_leads_to_use = MOCK_LEADS_BATCH_2
            
            # Increment batch index for next time
            st.session_state.demo_batch_index += 1
            
            # First Pass Container (simulated)
            first_pass_status = st.status("Running Public Lead Discovery...", expanded=True)
            with first_pass_status:
                st.write("Searching LinkedIn profiles...")
                progress_bar = st.progress(0)
                current_name_display = st.empty()
                
                temp_first_pass = []
                
                # Simulate delay
                time.sleep(2)
                
                total = len(mock_leads_to_use)
                for idx, mock_lead in enumerate(mock_leads_to_use):
                    # Process through first_pass scoring
                    combined = f"{mock_lead['title']} {mock_lead['snippet']}"
                    score, conf, breakdown, enriched_company = score_text(combined, query, mock_lead["url"])
                    
                    # Use mock enriched company if provided
                    if mock_lead.get("enriched_company"):
                        enriched_company = mock_lead["enriched_company"]
                    
                    name = mock_lead["name"]
                    
                    temp_first_pass.append({
                        "Name": name,
                        "Title": mock_lead["title"],
                        "Snippet": mock_lead["snippet"],
                        "URL": mock_lead["url"],
                        "Score": score,
                        "Confidence": conf,
                        "Signals": " | ".join(breakdown),
                        "Enriched Company": enriched_company
                    })
                    
                    # Update display (clears previous)
                    current_name_display.write(f"Found: **{name}**")
                    progress_bar.progress((idx + 1) / total)
                    time.sleep(0.1)
                
                first_pass_status.update(label="Public Lead Discovery Complete", state="complete")
            
            # Second Pass Container (simulated)
            temp_second_pass = []
            if temp_first_pass:
                second_pass_status = st.status("Running Automated Verification...", expanded=True)
                with second_pass_status:
                    st.write("Verifying investor credentials...")
                    verify_progress = st.progress(0)
                    current_verify_display = st.empty()
                    
                    for idx, person in enumerate(temp_first_pass):
                        name = person["Name"]
                        
                        # Update display
                        current_verify_display.write(f"Verifying: **{name}**")
                        
                        # Simulate verification delay (random 1-3 seconds per name)
                        delay = random.uniform(0.7, 2.1)
                        time.sleep(delay)
                        
                        # Simulate second pass scoring (simplified for demo)
                        temp_second_pass.append({
                            "Name": name,
                            "Query Used": f'"{name}" UAE investor',
                            "Snippet": person["Snippet"][:200],
                            "Second Pass Score": min(person["Score"] * 0.8, 10.0),
                            "Score Breakdown": "Simulated verification",
                            "Source URL": person["URL"]
                        })
                        
                        verify_progress.progress((idx + 1) / len(temp_first_pass))
                    
                    second_pass_status.update(label="Automated Verification Complete", state="complete")
            
            # Consolidation (same as live)
            st.session_state.dashboard_results.extend(temp_first_pass)
            st.session_state.dashboard_verified.extend(temp_second_pass)
            
            # Create consolidated results
            consolidated = []
            df_second = pd.DataFrame(st.session_state.dashboard_verified)
            
            for person in st.session_state.dashboard_results:
                name = person["Name"]
                first_pass_score = person["Score"]
                enriched_company = person.get("Enriched Company", "")
                url = person.get("URL", "")
                signals = person.get("Signals", "")
                title = person.get("Title", "")
                snippet = person.get("Snippet", "")
                
                # Extract keywords
                identity_kws = extract_keywords_from_signals(signals, identity_keywords)
                geo_kws = extract_keywords_from_signals(signals, uae_keywords + mena_keywords)
                seniority_kws = extract_keywords_from_signals(signals, seniority_keywords)
                
                # Check if verified
                if not df_second.empty and name in df_second["Name"].values:
                    person_verified = df_second[df_second["Name"] == name]
                    second_pass_total = min(person_verified["Second Pass Score"].sum(), 10.0)
                    final_score = (first_pass_score + second_pass_total) / 2
                else:
                    second_pass_total = 0.0
                    final_score = first_pass_score / 2
                
                # Determine verdict
                verdict = "Green List" if final_score >= 5.0 else "Red List"
                
                consolidated.append({
                    "Name": name,
                    "Company": enriched_company,
                    "Identity Keywords": identity_kws,
                    "Geo Keywords": geo_kws,
                    "Seniority Keywords": seniority_kws,
                    "Score": final_score,
                    "Final Verdict": verdict,
                    "URL": url,
                    "Title": title,
                    "Snippet": snippet,
                    "Signals": signals,
                    "Confidence": person.get("Confidence", "Low")
                })
            
            # Update results
            st.session_state.dashboard_results = []
            for item in consolidated:
                st.session_state.dashboard_results.append(item)
            
            st.success("Discovery Complete!")
            time.sleep(1)
            st.rerun()
        
        # ==================== LIVE MODE (DDGS) BRANCH ====================
        else:
            # Fixed query for UAE angel investors
            query = '"angel investor" UAE site:linkedin.com/in'
            max_results = 5
        
            # First Pass Container
            first_pass_status = st.status("Running First Pass Discovery...", expanded=True)
            with first_pass_status:
                st.write("Searching LinkedIn profiles...")
                progress_bar = st.progress(0)
                current_name_display = st.empty()  # For clearing previous names
                
                temp_first_pass = []
                
                with DDGS(timeout=10) as ddgs:
                    results_list = list(ddgs.text(query, max_results=max_results, backend="lite"))
                    total = len(results_list)
                    
                    for idx, r in enumerate(results_list):
                        url = r.get("href", "")
                        if not url:
                            continue
                        
                        if any(bad in normalize_url(url) for bad in blocked_urls):
                            continue
                        
                        title = soft_truncate_ellipsis(r.get("title", ""))
                        snippet = soft_truncate_ellipsis(r.get("body", ""))
                        
                        if " | LinkedIn" in title:
                            match = re.search(r'(\s*[-–—]?\s*\|\s*LinkedIn)', title)
                            if match:
                                cut_idx = match.start()
                                title = title[:cut_idx + len(match.group(0))].strip()
                            else:
                                parts = title.split(" | LinkedIn")
                                title = parts[0].strip() + " | LinkedIn"
                        
                        if is_duplicate_url(url, st.session_state.dashboard_results, title, snippet):
                            continue
                        
                        combined = f"{title} {snippet}"
                        score, conf, breakdown, enriched_company = score_text(combined, query, url)
                        name = extract_name(title)
                        
                        if not is_valid_person_name(name):
                            continue
                        
                        existing_idx = find_existing_person(url, st.session_state.dashboard_results)
                        if existing_idx is not None:
                            existing = st.session_state.dashboard_results[existing_idx]
                            # Safely update existing entry with .get() methods
                            if "Snippet" in existing:
                                existing["Snippet"] += "\n---\n" + snippet
                            existing["Score"] = max(existing.get("Score", 0), score)
                            old_signals = set(existing.get("Signals", "").split(" | "))
                            new_signals = set(breakdown)
                            existing["Signals"] = " | ".join(sorted(old_signals | new_signals))
                            if conf == "High":
                                existing["Confidence"] = "High"
                            elif conf == "Medium" and existing.get("Confidence") == "Low":
                                existing["Confidence"] = "Medium"
                        else:
                            temp_first_pass.append({
                                "Name": name,
                                "Title": title,
                                "Snippet": snippet,
                                "URL": url,
                                "Score": score,
                                "Confidence": conf,
                                "Signals": " | ".join(breakdown),
                                "Enriched Company": enriched_company
                            })
                            # Update the display with current name (clears previous)
                            current_name_display.write(f"Found: **{name}**")
                        
                        progress_bar.progress((idx + 1) / total)
                        time.sleep(0.1)
                
                first_pass_status.update(label="First Pass Complete", state="complete")
            
            # Second Pass Container
            temp_second_pass = []  # Initialize here to prevent NameError if temp_first_pass is empty
            if temp_first_pass:
                second_pass_status = st.status("Running Second Pass Verification...", expanded=True)
                with second_pass_status:
                    st.write("Verifying investor credentials. Please wait...")
                    verify_progress = st.progress(0)
                    current_verify_display = st.empty()  # For clearing previous names
                    
                    temp_second_pass = []  # Reset for this verification run
                    
                    for idx, person in enumerate(temp_first_pass):
                        name = person["Name"]
                        enriched_company = person.get("Enriched Company", "")
                        snippet = person.get("Snippet", "")
                        
                        # Update the display with current name (clears previous)
                        current_verify_display.write(f"Verifying: **{name}**")
                        
                        anchors = second_pass.extract_anchors(snippet)
                        queries = second_pass.build_second_pass_queries(name, anchors, enriched_company)
                        
                        state = {
                            "identity_confirmed": False,
                            "geo_hits": 0,
                            "linkedin_hits": 0,
                            "domain_hits": set(),
                            "expected_name": name
                        }
                        
                        with DDGS(timeout=10) as ddgs:
                            for q in queries[:2]:
                                try:
                                    verification_results = list(ddgs.text(q, max_results=3, backend="lite"))
                                    
                                    for vr in verification_results:
                                        url = vr.get("href", "")
                                        if not url:
                                            continue
                                        
                                        text = f"{vr.get('title', '')} {vr.get('body', '')}"
                                        score2, breakdown2, confirmed = second_pass.score_second_pass(text, url, state)
                                        
                                        if score2 > 0:
                                            temp_second_pass.append({
                                                "Name": name,
                                                "Query Used": q,
                                                "Snippet": text,
                                                "Second Pass Score": score2,
                                                "Score Breakdown": " | ".join(breakdown2),
                                                "Source URL": url
                                            })
                                    
                                    time.sleep(0.5)
                                except Exception as e:
                                    continue
                        
                        verify_progress.progress((idx + 1) / len(temp_first_pass))
                        time.sleep(0.1)
                    
                    second_pass_status.update(label="Verification Complete", state="complete")
            
            # Consolidation
            st.session_state.dashboard_results.extend(temp_first_pass)
            st.session_state.dashboard_verified.extend(temp_second_pass)
            
            # Create consolidated results
            consolidated = []
            df_second = pd.DataFrame(st.session_state.dashboard_verified)
            
            for person in st.session_state.dashboard_results:
                name = person["Name"]
                first_pass_score = person["Score"]
                enriched_company = person.get("Enriched Company", "")
                url = person.get("URL", "")
                signals = person.get("Signals", "")
                title = person.get("Title", "") # Added to preserve metadata
                snippet = person.get("Snippet", "") # Added to preserve metadata
                
                # Extract keywords
                identity_kws = extract_keywords_from_signals(signals, identity_keywords)
                geo_kws = extract_keywords_from_signals(signals, uae_keywords + mena_keywords)
                seniority_kws = extract_keywords_from_signals(signals, seniority_keywords)
                
                # Check if verified
                if not df_second.empty and name in df_second["Name"].values:
                    person_verified = df_second[df_second["Name"] == name]
                    second_pass_total = min(person_verified["Second Pass Score"].sum(), 10.0)
                    final_score = (first_pass_score + second_pass_total) / 2
                else:
                    second_pass_total = 0.0
                    final_score = first_pass_score / 2
                
                # Determine verdict
                verdict = "Green List" if final_score >= 5.0 else "Red List"
                
                consolidated.append({
                                "Name": name,
                                "Company": enriched_company,
                                "Identity Keywords": identity_kws,
                                "Geo Keywords": geo_kws,
                                "Seniority Keywords": seniority_kws,
                                "Score": final_score,
                                "Final Verdict": verdict,
                                "URL": url,
                                "Title": person.get("Title", ""),
                                "Snippet": person.get("Snippet", ""),
                                "Signals": signals,
                                "Confidence": person.get("Confidence", "Low")
                            })
        
        # Update results in session state
        st.session_state.dashboard_results = []
        for item in consolidated:
            st.session_state.dashboard_results.append(item)
        
        st.success("Discovery Complete!")
        time.sleep(3)
        st.rerun()
    
    # ==================== FILTER TOGGLE ====================
    if st.session_state.dashboard_results:
        st.markdown("---")
        show_green_only = st.checkbox("Show Green List Only", value=False)
        
        # Filter results
        display_results = st.session_state.dashboard_results
        if show_green_only:
            display_results = [r for r in display_results if r.get("Final Verdict") == "Green List"]
        
        # Sort: enriched companies first. Maybe use later
        #display_results = sorted(
        #    display_results,
        #    key=lambda x: (x.get("Company", "") == "", -x.get("Score", 0))
        #)
        
        # ==================== DISPLAY CARDS ====================
        st.markdown("### Investor Leads")
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Display cards in 2-column layout
        for i in range(0, len(display_results), 2):
            col1, col2 = st.columns(2)
            
            # First card in row
            with col1:
                result = display_results[i]
                name = result.get("Name", "Unknown")
                company = result.get("Company", "")
                identity_kws = result.get("Identity Keywords", [])
                geo_kws = result.get("Geo Keywords", [])
                seniority_kws = result.get("Seniority Keywords", [])
                score = result.get("Score", 0)
                verdict = result.get("Final Verdict", "Red List")
                url = result.get("URL", "#")
                
                # Verdict badge
                verdict_class = "badge-green" if verdict == "Green List" else "badge-red"
                
                # Create card HTML
                card_html = f"""
                <div class="investor-card">
                    <div class="investor-name">{name}</div>
                    {f'<div class="investor-company">at {company}</div>' if company else ''}
                    
                    <div style="margin-bottom: 12px;">
                        {''.join([f'<span class="badge badge-identity">{format_badge_text(kw)}</span>' for kw in identity_kws[:3]])}
                        {''.join([f'<span class="badge badge-seniority">{format_badge_text(kw)}</span>' for kw in seniority_kws[:3]])}
                        {''.join([f'<span class="badge badge-geo">{format_badge_text(kw)}</span>' for kw in geo_kws[:3]])}
                    </div>
                    
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 16px;">
                        <span class="badge {verdict_class}">{verdict}</span>
                        <a href="{url}" target="_blank" class="linkedin-btn">View LinkedIn</a>
                    </div>

                    <div class="progress-container">
                        <div class="progress-label">AI Confidence: {score:.1f}/10</div>
                        <div class="progress-bar-bg">
                            <div class="progress-bar-fill" style="width: {(score/10)*100}%"></div>
                        </div>
                    </div>
                </div>
                """
                                
                st.html(card_html)
                
                # Progress column for AI Confidence
                #st.progress(score / 10, text=f"AI Confidence: {score:.1f}/10")
                #st.markdown("<br>", unsafe_allow_html=True)
            
            # Second card in row (if exists)
            if i + 1 < len(display_results):
                with col2:
                    result = display_results[i + 1]
                    name = result.get("Name", "Unknown")
                    company = result.get("Company", "")
                    identity_kws = result.get("Identity Keywords", [])
                    geo_kws = result.get("Geo Keywords", [])
                    seniority_kws = result.get("Seniority Keywords", [])
                    score = result.get("Score", 0)
                    verdict = result.get("Final Verdict", "Red List")
                    url = result.get("URL", "#")
                    
                    # Verdict badge
                    verdict_class = "badge-green" if verdict == "Green List" else "badge-red"
                    
                    # Create card HTML
                    card_html = f"""
                    <div class="investor-card">
                        <div class="investor-name">{name}</div>
                        {f'<div class="investor-company">at {company}</div>' if company else ''}
                        
                        <div style="margin-bottom: 12px;">
                            {''.join([f'<span class="badge badge-identity">{format_badge_text(kw)}</span>' for kw in identity_kws[:3]])}
                            {''.join([f'<span class="badge badge-seniority">{format_badge_text(kw)}</span>' for kw in seniority_kws[:3]])}
                            {''.join([f'<span class="badge badge-geo">{format_badge_text(kw)}</span>' for kw in geo_kws[:3]])}
                        </div>
                        
                        <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 16px;">
                            <span class="badge {verdict_class}">{verdict}</span>
                            <a href="{url}" target="_blank" class="linkedin-btn">View LinkedIn</a>
                        </div>

                        <div class="progress-container">
                            <div class="progress-label">AI Confidence: {score:.1f}/10</div>
                            <div class="progress-bar-bg">
                                <div class="progress-bar-fill" style="width: {(score/10)*100}%"></div>
                            </div>
                        </div>
                    </div>
                    """
                    
                    st.html(card_html)
                    
                    # Progress column for AI Confidence
                    #st.progress(score / 10, text=f"AI Confidence: {score:.1f}/10")
                    #st.markdown("<br>", unsafe_allow_html=True)
        
        # ==================== DISCOVER MORE & DOWNLOAD CSV ====================
        st.markdown("---")
        
        # Discover More Button
        col_more1, col_more2, col_more3 = st.columns([1, 2, 1])
        with col_more2:
            discover_more_button = st.button("Discover More", use_container_width=True)
        
        if discover_more_button:
            # Trigger discovery without creating a new section
            st.session_state.trigger_discovery = True
            st.rerun()
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Prepare CSV data
        csv_data = []
        for r in display_results:
            csv_data.append({
                "Name": r.get("Name", ""),
                "Company": r.get("Company", ""),
                "Identity Keywords": ", ".join(r.get("Identity Keywords", [])),
                "Seniority Keywords": ", ".join(r.get("Seniority Keywords", [])),
                "Geo Keywords": ", ".join(r.get("Geo Keywords", [])),
                "AI Confidence Score": f"{r.get('Score', 0):.1f}",
                "Verdict": r.get("Final Verdict", ""),
                "LinkedIn URL": r.get("URL", "")
            })
        
        df_download = pd.DataFrame(csv_data)
        csv = df_download.to_csv(index=False).encode('utf-8')
        
        col_dl1, col_dl2, col_dl3 = st.columns([1, 2, 1])
        with col_dl2:
            st.download_button(
                label="Import Leads to Excel",
                data=csv,
                file_name="uae_investor_leads.csv",
                mime="text/csv",
                use_container_width=True
            )

         # ==================== FOOTER ====================
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown(
            "<p style='text-align: center; color: #9CA3AF; font-size: 0.875rem; padding: 20px 0;'>"
            "TekhLeads Dashboard for UAE Investor Discovery"
            "</p>", 
            unsafe_allow_html=True
        )   
