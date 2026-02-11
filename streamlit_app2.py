import streamlit as st
from ddgs import DDGS
import pandas as pd
import re
import time
import joblib
import numpy as np

from first_pass import (score_text, identity_keywords, behavior_keywords, uae_keywords, mena_keywords)
import second_pass 
from dashboard import run_dashboard
from ml import (run_ml_trainer, clean_key, build_feature_vector)

ml_brain = None
feature_columns = None

try:
    model_package = joblib.load("model.pkl")
    ml_brain = model_package["model"]
    feature_columns = model_package["feature_columns"]
except:
    ml_brain = None


if "first_pass_results" not in st.session_state:
    st.session_state.first_pass_results = []
if "second_pass_results" not in st.session_state:
    st.session_state.second_pass_results = []

st.sidebar.title("Sidebar")
choice = st.sidebar.radio("Switch View:", ["Dashboard", "Testing dashboard", "AI model generation"])

if choice == "Dashboard":
    run_dashboard()
elif choice == "AI model generation":
    run_ml_trainer()
else:

    st.set_page_config(page_title="Leads Dashboard", layout="wide")
    st.title("Leads Dashboard")

    blocked_urls = [
        "bing.com/aclick",
        "bing.com/ck/a",
        "doubleclick.net"
    ]

    # HELPER FUNCTIONS 

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
    
    def clean_key(text):
        return text.strip().upper().replace(" ", "_")
    
    def clean_signal(text):
        if "(+" in text:
            return text.split("(+")[0].strip()
        return text.strip()

    def build_feature_vector(fp_signals, sp_signals, expected_columns):
        features = {}

        for sig in fp_signals:
            cleaned = clean_signal(sig)
            key = f"FP_HAS_{clean_key(cleaned)}"
            features[key] = 1

        for sig in sp_signals:
            cleaned = clean_signal(sig)
            key = f"SP_HAS_{clean_key(cleaned)}"
            features[key] = 1

        df = pd.DataFrame([features]).fillna(0)

        for col in expected_columns:
            if col not in df.columns:
                df[col] = 0

        return df[expected_columns]

    # FIRST PASS

    st.subheader("Public Lead Discovery")

    query_input = st.text_area(
        "Enter search queries (one per line)",
        height=100,
        placeholder='"angel investor" UAE site:linkedin.com/in'
    )

    max_results_per_query = st.number_input("Results per query", 1, 50, 10)

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

                    if " | LinkedIn" in title:
                        match = re.search(r'(\s*[-–—]?\s*\|\s*LinkedIn)', title)
                        if match:
                            cut_idx = match.start()
                            title = title[:cut_idx + len(match.group(0))].strip()
                        else:
                            parts = title.split(" | LinkedIn")
                            title = parts[0].strip() + " | LinkedIn"
                    
                    if is_duplicate_url(url, st.session_state.first_pass_results, title, snippet):
                        continue

                    combined = f"{title} {snippet}"
                    score, conf, breakdown, enriched_company = score_text(combined, query, url)
                    name = extract_name(title)

                    if not is_valid_person_name(name):
                        continue

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

    if not df_first.empty:
        st.dataframe(
            df_first[["Name", "Title", "Snippet", "Enriched Company", "Score", "Confidence", "Signals", "URL"]],
            use_container_width=True
        )

    # SECOND PASS

    st.divider()
    st.subheader("2. Automated Verification")

    if st.button("Run Second Pass Verification"):
        if df_first.empty:
            st.error("No leads to verify.")
        else:
            # Filter: Only verify leads that scored reasonably well in Pass 1
            SECOND_PASS_THRESHOLD = 5.0
            candidates = df_first[df_first["Score"] >= SECOND_PASS_THRESHOLD]
            total = len(candidates)
            
            verify_progress = st.progress(0)
            status_text = st.empty()
            
            processed_names = {x["Name"] for x in st.session_state.second_pass_results}
            
            with DDGS(timeout=10) as ddgs:
                for i, (_, row) in enumerate(candidates.iterrows()):
                    name = row["Name"]
                    if name in processed_names: continue

                    # Skip incomplete or duplicate names
                    name_parts = name.strip().split()
                    last_name = name_parts[-1] if len(name_parts) > 1 else ""
                    first_name = name_parts[0] if len(name_parts) > 0 else ""

                    # Single-letter last name
                    # First name == last name (repeated name)
                    if len(name_parts) < 2 or len(last_name) == 1 or first_name.lower() == last_name.lower():
                        # Directly add to consolidation (first-pass only)
                        st.session_state.second_pass_results.append({
                            "Name": name,
                            "Query Used": "",
                            "Title": row.get("Title",""),
                            "Snippet": row.get("Snippet",""),
                            "Second Pass Score": 0.0,
                            "Score Breakdown": "Skipped second pass due to incomplete/common name",
                            "Source URL": row.get("URL","")
                        })
                        continue

                    status_text.write(f"Verifying: **{name}** ({i+1}/{total})")
                    verify_progress.progress((i + 1) / total)
                    
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
                    
                    seen_urls = set()
                    candidate_verified_data = []
                    
                    for q in queries:
                        # Rate Limiting / optimization
                        if state["identity_confirmed"] and state["geo_hits"] >= 1:
                            break
                            
                        time.sleep(1.0) 
                        status_text.write(f"Querying: {q}")

                        try:
                            results = list(ddgs.text(q, max_results=20, backend="html")) 
                        except Exception: 
                            continue
                            
                        for r in results:
                            url = r.get("href", "")
                            if not url: continue
                            
                            norm_url = normalize_url(url)
                            if any(bad in norm_url for bad in blocked_urls): continue
                            if url in seen_urls: continue
                            seen_urls.add(url)

                            text = f"{r.get('title','')} {r.get('body','')}"
                            score2, breakdown2, _ = second_pass.score_second_pass(text, url, state)
                            
                            if score2 > 0:
                                candidate_verified_data.append({
                                    "Name": name,
                                    "Query Used": q,
                                    "Snippet": text,
                                    "Second Pass Score": score2,
                                    "Score Breakdown": " | ".join(breakdown2),
                                    "Source URL": url
                                })
                                
                    if candidate_verified_data:
                        st.session_state.second_pass_results.extend(candidate_verified_data)
            
            status_text.success("Verification Complete.")
            verify_progress.empty()

    df_second = pd.DataFrame(st.session_state.second_pass_results)

    if not df_second.empty:
        st.dataframe(df_second[["Name", "Query Used", "Snippet", "Second Pass Score", "Score Breakdown", "Source URL"]], use_container_width=True)

    # Fixed Logic

    def is_address_like(text):
        if not text: return False
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

        # 1. Process leads that WENT THROUGH verification
        if not df_second.empty:
            for name, g in df_second.groupby("Name"):
                # Cumulative scoring for Second Pass (capped at 10)
                # SUM of scores, capped at 10.
                second_pass_total = min(g["Second Pass Score"].sum(), 10.0)
                
                # Retrieve First Pass Score
                first_pass_row = df_first[df_first["Name"] == name].iloc[0]
                first_pass_score = first_pass_row["Score"]

                # Calculate FINAL AVERAGED SCORE
                final_score = (first_pass_score + second_pass_total) / 2
                
                # Breakdown Analysis
                all_breakdowns_text = " | ".join(g["Score Breakdown"].astype(str)).lower()
                
                investor_confirmed = "Yes" if "investor identity" in all_breakdowns_text else "No"
                uae_confirmed = "Yes" if "geography" in all_breakdowns_text else "No"
                
                # Enrichment Check
                sources = []
                if any("rocketreach.co" in url.lower() for url in g["Source URL"]):
                    sources.append("RocketReach")
                if any("zoominfo.com" in url.lower() for url in g["Source URL"]):
                    sources.append("ZoomInfo")
                if any("yello.ae" in url.lower() for url in g["Source URL"]):
                    sources.append("Yello.ae")    
                if any("linkedin.com/company/" in url.lower() for url in g["Source URL"]):
                    sources.append("Company information inside LinkedIn")

                enriched_social = ""
                if sources:
                    enriched_social = f"Yes ({', '.join(sources)})"

                # Verdict Logic (Based on Average)
                if final_score >= 8.4:
                    verdict = "GREAT"  # High confidence on both, or Perfect on one and good on other
                elif final_score >= 5.0:
                    verdict = "GOOD"    # Solid lead, maybe second pass was weak but first pass was great
                else:
                    verdict = "REJECT"

                # Company cleanup
                snippets = g["Snippet"].tolist()
                companies = set()
                for s in snippets:
                    matches = re.findall(r"\b(at|with)\s+([A-Z][A-Za-z0-9 &]{3,})", s)
                    for _, company in matches:
                        if not is_address_like(company): companies.add(company.strip())
                
                final_company = first_pass_row.get("Enriched Company", "")
                if not final_company and companies:
                    final_company = ", ".join(list(companies)[:1])

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
                    verdict = "REJECT"
                    investor = "No"
                    uae = "No"   

                # ML Prediction Logic
                ml_id, ml_beh, ml_geo, ml_avg = 0.0, 0.0, 0.0, 0.0

                if ml_brain and feature_columns:

                    # Robust split that handles both ", " and " | "
                    def robust_split(text):
                        if not text:
                            return []
                        # Split on comma or |, then strip
                        parts = re.split(r'\s*[,|]\s*', str(text))
                        return [p.strip() for p in parts if p.strip()]

                    # First-pass signals (from df_first)
                    fp_signals = str(first_pass_row.get("Signals", ""))
                    fp_signals_list = [clean_signal(s) for s in robust_split(fp_signals)]

                    # Second-pass signals (from Score Breakdown)
                    sp_signals_raw = []
                    for breakdown in g["Score Breakdown"].dropna():
                        sp_signals_raw.extend(robust_split(breakdown))
                    sp_signals_list = list(set(sp_signals_raw))   # unique

                    df_input = build_feature_vector(
                        fp_signals_list,
                        sp_signals_list,
                        feature_columns
                    )

                    preds = ml_brain.predict(df_input)[0]
                    ml_id, ml_beh, ml_geo = np.clip(preds, 1, 10)
                    ml_avg = round((ml_id + ml_beh + ml_geo) / 3, 1)
            
                consolidated.append({
                    "Name": name,
                    #"ML_Behavior": round(ml_beh, 1),
                    #"ML_Geo": round(ml_geo, 1),
                    #"ML_Final_Score": ml_avg,
                    "Investor Confirmed": investor_confirmed,
                    "UAE Confirmed": uae_confirmed,
                    "Enriched Company": final_company,
                    "Enriched Social": enriched_social,
                    "First Pass Score": round(first_pass_score, 1),
                    "Second Pass Score": round(second_pass_total, 1),
                    "Final Score": round(final_score, 1),
                    "AI Powered Score": round(ml_id, 1),
                    "Final Verdict": verdict
                })

        # Process leads that were SKIPPED (Pending)
        pending_names = all_first_pass_names - verified_names
        for name in pending_names:
            row = df_first[df_first["Name"] == name].iloc[0]
            # Only show pending if they had a decent first pass score
            if row["Score"] >= 5:
                consolidated.append({
                    "Name": name,
                    "First Pass Score": round(row["Score"], 1),
                    "Second Pass Score": 0.0,
                    "Final Score": round(row["Score"] / 2, 1),
                    "Investor Confirmed": "Pending",
                    "UAE Confirmed": "Pending",
                    "Enriched Company": row.get("Enriched Company", ""),
                    "Enriched Social": "No",
                    "Final Verdict": "PENDING"
                })

        df_consolidated = pd.DataFrame(consolidated)
        
        if not df_consolidated.empty:
            # Sort by Final Score
            st.dataframe(
                df_consolidated.sort_values(by="Final Score", ascending=False),
                use_container_width=True
            )
            
            # Metrics
            c1, c2 = st.columns(2)
            total_count = len(df_consolidated[df_consolidated["Final Verdict"] == "GREAT"]) + len(df_consolidated[df_consolidated["Final Verdict"] == "GOOD"])
            c1.metric("Green List", total_count)
            c2.metric("Review Pending/Discarded", len(df_consolidated[df_consolidated["Final Verdict"] == "PENDING"]))
