import streamlit as st
from ddgs import DDGS
import pandas as pd
import re
import time

# Import logic
from first_pass import (score_text, identity_keywords, behavior_keywords, uae_keywords, mena_keywords)
import second_pass 

# --- SESSION STATE SETUP ---
if "first_pass_results" not in st.session_state:
    st.session_state.first_pass_results = []
if "second_pass_results" not in st.session_state:
    st.session_state.second_pass_results = []

st.set_page_config(page_title="Leads Dashboard", layout="wide")
st.title("Investor Lead Discovery System")

blocked_urls = [
    "bing.com/aclick",
    "bing.com/ck/a",
    "doubleclick.net"
]

# --- HELPER FUNCTIONS (Restored from your snippet) ---

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
            # If text is very similar, it's a dupe
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

# --- SECTION 1: DISCOVERY (FIRST PASS) ---

st.subheader("1. Public Lead Discovery")

query_input = st.text_area(
    "Enter search queries (one per line)",
    height=100,
    placeholder='"angel investor" UAE site:linkedin.com/in'
)

max_results_per_query = st.number_input("Results per query", 1, 50, 15)

if st.button("Run Discovery"):
    queries = [q.strip() for q in query_input.split("\n") if q.strip()]
    
    st.write(f"Running {len(queries)} queries...")
    progress_bar = st.progress(0)
    
    with DDGS(timeout=10) as ddgs:
        for q_idx, query in enumerate(queries):
            results_list = list(ddgs.text(query, max_results=max_results_per_query, backend="lite"))
            
            for r in results_list:
                url = r.get("href", "")
                if not url: continue

                if any(bad in normalize_url(url) for bad in blocked_urls):
                    continue                

                title = soft_truncate_ellipsis(r.get("title", ""))
                snippet = soft_truncate_ellipsis(r.get("body", ""))
                
                # Check Duplicates
                if is_duplicate_url(url, st.session_state.first_pass_results, title, snippet):
                    continue

                # Score
                combined = f"{title} {snippet}"
                score, conf, breakdown, enriched_company = score_text(combined, query, url)
                name = extract_name(title)

                if not is_valid_person_name(name):
                    continue

                # Upsert Logic
                existing_idx = find_existing_person(url, st.session_state.first_pass_results)
                if existing_idx is not None:
                    existing = st.session_state.first_pass_results[existing_idx]

                    existing["Snippet"] += "\n---\n" + snippet
                    existing["Title"] = existing["Title"]
                    existing["Score"] = max(existing["Score"], score)

                    old_signals = set(existing["Signals"].split(" | "))
                    new_signals = set(breakdown)
                    existing["Signals"] = " | ".join(sorted(old_signals | new_signals))

                    if conf == "High":
                        existing["Confidence"] = "High"
                    elif conf == "Medium" and existing["Confidence"] == "Low":
                        existing["Confidence"] = "Medium"

                else:
                    st.session_state.first_pass_results.append({
                        "Reviewed": False,
                        "Name": name,
                        "Title": title,
                        "Snippet": snippet,
                        "URL": url,
                        "Score": score,
                        "Confidence": conf,
                        "Signals": " | ".join(breakdown),
                        "Enriched Company": enriched_company
                    })
            
            progress_bar.progress((q_idx + 1) / len(queries))

EXPECTED_COLUMNS = [
    "Name", "Title", "Snippet",
    "URL", "Score", "Confidence", "Signals", "Enriched Company"
]

df_first = pd.DataFrame(st.session_state.first_pass_results)

for col in EXPECTED_COLUMNS:
    if col not in df_first.columns:
        df_first[col] = []

st.dataframe(
    df_first[["Name", "Title", "Snippet", "Enriched Company", "Score", "Confidence", "Signals", "URL"]],
    use_container_width=True
)

# --- SECTION 2: VERIFICATION (SECOND PASS) ---

st.divider()
st.subheader("2. Automated Verification")

if st.button("Run Second Pass Verification"):
    if df_first.empty:
        st.error("No leads to verify.")
    else:
        # Filter for candidates
        SECOND_PASS_THRESHOLD = 5.0
        candidates = df_first[df_first["Score"] >= SECOND_PASS_THRESHOLD]

        total = len(candidates)
        
        verify_progress = st.progress(0)
        status_text = st.empty()
        
        # Track processed names to avoid re-running same session
        processed_names = {x["Name"] for x in st.session_state.second_pass_results}
        
        with DDGS(timeout=10) as ddgs:
            for i, (_, row) in enumerate(candidates.iterrows()):
                name = row["Name"]
                if name in processed_names: continue

                # --- HARD SKIP: Incomplete names (single-letter last name) ---
                name_parts = name.strip().split()

                if len(name_parts) < 2 or len(name_parts[-1]) == 1:
                    # Send directly to consolidation, never second pass
                    continue
                
                status_text.write(f"Verifying: **{name}** ({i+1}/{total})")
                verify_progress.progress((i + 1) / total)
                
                # Setup
                anchors = second_pass.extract_anchors(row["Snippet"])
                queries = second_pass.build_second_pass_queries(name, anchors, row["Enriched Company"])
                
                state = {
                    "linkedin_seen": False,
                    "geo_hits": 0,
                    "identity_confirmed": False,
                    "domain_hits": set(),
                    "expected_name": name.lower(),
                    "first_pass_keywords": set(
                        identity_keywords + behavior_keywords
                    ),
                    "linkedin_hits": 0
                }
                
                # Search Loop
                seen_urls = set()
                candidate_verified_data = []
                
                for q in queries:
                    # Smart Rate Limiting: Stop if we already confirmed identity strongly
                    if state["identity_confirmed"] and state["geo_hits"] >= 1:
                        break
                        
                    time.sleep(0.5) # Polite delay
                    status_text.write(f"Querying: {q}")

                    try:
                        results = list(ddgs.text(q, max_results=12, backend="html"))
                    except Exception: 
                        continue
                        
                    for r in results:
                        url = r.get("href", "")
                        if not url: continue

                        norm_url = normalize_url(url)
                        if any(bad in norm_url for bad in blocked_urls):
                            continue

                        if url in seen_urls:
                            continue

                        seen_urls.add(url)

                        title = str(r.get('title', ''))
                        text = f"{r.get('title','')} {r.get('body','')}"
                        score2, breakdown2, id_conf = second_pass.score_second_pass(text, url, state)
                        
                        if score2 > 0:
                            candidate_verified_data.append({
                            "Name": name,
                            "Query Used": q,
                            "Title": title,
                            "Snippet": text,
                            "Second Pass Score": score2,
                            "Score Breakdown": " | ".join(breakdown2),
                            "Source URL": url
                        })
                            
                # Add best results to session state
                if candidate_verified_data:
                    st.session_state.second_pass_results.extend(candidate_verified_data)
        
        status_text.success("Verification Complete.")
        verify_progress.empty()

df_second = pd.DataFrame(st.session_state.second_pass_results)

if "Title" not in df_second.columns:
    df_second["Title"] = ""

if not df_second.empty:
    st.dataframe(df_second[["Name", "Query Used", "Title","Snippet", "Second Pass Score", "Score Breakdown", "Source URL"]], use_container_width=True)

# --- SECTION 3: CONSOLIDATION (Your Logic) ---

def is_address_like(text):
    if not text:
        return False
    return any(k in text.lower() for k in [
        "building", "street", "road", "avenue",
        "precinct", "floor", "office", "po box"
    ])

st.divider()
st.subheader("3. Consolidation & Verdict")

if not df_first.empty:
    consolidated = []
    
    verified_names = set(df_second["Name"]) if not df_second.empty else set()
    all_first_pass_names = set(df_first["Name"])

    # Process Verified Leads
    if not df_second.empty:
        for name, g in df_second.groupby("Name"):
            # Logic: Sum raw score, cap at 6.0
            total_raw = g["Second Pass Score"].sum()
            total = min(total_raw, 6.0)

            # Extract breakdown signals
            all_breakdowns = [item for sublist in g["Score Breakdown"] for item in sublist]
            
            investor = "Yes" if any("Confirmed investor identity" in x for x in all_breakdowns) else "No"
            uae = "Yes" if any("geography" in x.lower() for x in all_breakdowns) else "No"
            
            snippets = g["Snippet"].tolist()
            first_pass_company = df_first[df_first["Name"] == name]["Enriched Company"].dropna().iloc[0]
            first_pass_row = df_first[df_first["Name"] == name].iloc[0]

            companies = set()
            for s in snippets:
                matches = re.findall(r"\b(at|with)\s+([A-Z][A-Za-z0-9 &]{3,})", s)
                for _, company in matches:
                    companies.add(company.strip())

            # Rocketreach check
            has_rocketreach = any("rocketreach.co" in u for u in g["Source URL"])
            
            if total >= 4.5:
                evidence_strength = "Strong"
            elif total >= 2.5:
                evidence_strength = "Moderate"
            else:
                evidence_strength = "Weak"

            # Verdict Logic
            if investor == "Yes" and uae == "Yes" and total >= 4.5:
                verdict = "ACCEPT"
            elif total >= 2.5:
                verdict = "GOOD"
            else:
                verdict = "REJECT"

            final_company = first_pass_company

            if not final_company:
                clean_companies = [
                    c for c in companies
                    if c and not is_address_like(c)
                ]
                if clean_companies:
                    final_company = ", ".join(sorted(set(clean_companies)))
            
            first_snippet = str(first_pass_row.get("Snippet", ""))

            second_snippets = ""
            if "Snippet" in g.columns:
                second_snippets = " ".join(
                    str(s) for s in g["Snippet"].dropna().tolist()
                )

            geo_text = f"{first_snippet} {second_snippets}".lower()

            either_have_geo_signal = any(
                k in geo_text for k in (uae_keywords + mena_keywords)
            )

            if not either_have_geo_signal:
                verdict = "REJECTED"
                investor = "No"
                uae = "No"

            consolidated.append({
                "Name": name,
                "First Pass Score": df_first[df_first["Name"] == name]["Score"].max(),
                "Second Pass Total": round(total, 1),
                "Evidence Rows": len(g),
                "Investor Confirmed": investor,
                "UAE Confirmed": uae,
                "Enriched Company": final_company,
                "Enriched Social": "Yes (RocketReach)" if has_rocketreach else "",
                "Evidence Strength": evidence_strength,
                "Final Verdict": verdict
            })

    # Process Pending Leads
    pending_names = all_first_pass_names - verified_names
    for name in pending_names:
        row = df_first[df_first["Name"] == name].iloc[0]
        if row["Score"] >= 3.8:
            consolidated.append({
                "Name": name,
                "First Pass Score": row["Score"],
                "Second Pass Total": 0.0,
                "Evidence Rows": 0,
                "Investor Confirmed": "Pending",
                "UAE Confirmed": "Pending",
                "Enriched Company": "",
                "Enriched Social": "",
                "Final Verdict": "PENDING"
            })

    df_consolidated = pd.DataFrame(consolidated)
    
    if not df_consolidated.empty:
        # Sort: ACCEPT/GOOD first
        st.dataframe(
            df_consolidated.sort_values(by="Second Pass Total", ascending=False),
            use_container_width=True
        )
        
        # Quick Metrics
        st.metric("Green List (Accept/Good)", len(df_consolidated[df_consolidated["Final Verdict"].isin(["ACCEPT", "GOOD"])]))
