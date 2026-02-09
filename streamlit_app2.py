import streamlit as st
from ddgs import DDGS
import pandas as pd
import re

if "results" not in st.session_state:
    st.session_state.results = []

st.set_page_config(page_title="Leads Dashboard", layout="wide")
st.title("Leads Discovery")

BASE_SCORE = 2.0
IDENTITY_WEIGHT = 2.5
IDENTITY_DIMINISHING_WEIGHT = 0.8
BEHAVIOR_WEIGHT = 0.4
BEHAVIOR_GROUP_BONUS = 0.5
SENIORITY_WEIGHT = 1.0
SENIORITY_GROUP_BONUS = 0.5
GEO_GROUP_BONUS = 0.6

identity_keywords = [
    "angel investor", "angel investing", "family office",
    "venture partner", "chief investment officer", "cio",
    "founder", "co-founder", "ceo", "incubator"
]

behavior_keywords = [
    "invested in", "investing in", "portfolio",
    "seed", "pre-seed", "early-stage", "funding",
    "venture capital", "private equity", "real estate",
    "fundraising", "investment portfolio", "wealth funds"
]

seniority_keywords = [
    "partner", "managing director", "chairman",
    "board member", "advisor", "advisory"
]

uae_keywords = ["uae", "dubai", "abu dhabi", "emirates"]
mena_keywords = ["mena", "middle east", "gulf"]

blocked_urls = [
    "bing.com/aclick",
    "bing.com/ck/a",
    "doubleclick.net"
]

QUERY_BLOCKLIST = {"partner", "ceo", "co-founder"}

def is_duplicate_url(url, existing_results, title, snippet):
    norm = normalize_url(url)
    for r in existing_results:
        if normalize_url(r.get("URL", "")) == norm:
            old_text = (r.get("Title","") + r.get("Snippet","")).lower()
            new_text = (title + snippet).lower()
            if len(set(new_text.split()) - set(old_text.split())) < 5:
                return True
    return False

def normalize_url(url):
    return url.split("?")[0].lower().strip()

def soft_truncate_ellipsis(text: str) -> str:
    if not text:
        return text
    if "..." in text:
        return text.split("...")[0].strip()
    return text

def find_existing_person(url, existing_results):
    norm = normalize_url(url)
    for i, r in enumerate(existing_results):
        if normalize_url(r.get("URL", "")) == norm:
            return i
    return None

def score_text(text, query, url=""):
    breakdown = []
    signal_groups = set()

    text_original = text
    text = text.lower()
    score = BASE_SCORE

    hashtags = re.findall(r'#(\w+)', text.lower())
    hashtag_hits = []

    HASHTAG_MULTIPLIER = 1.0

    for tag in hashtags:
        tag_text = tag.replace("_", " ")

        if tag_text in identity_keywords:
            boost = IDENTITY_WEIGHT * HASHTAG_MULTIPLIER
            score += boost
            hashtag_hits.append(f"#{tag} = identity (+{round(boost,1)})")
            signal_groups.add("Identity")

        elif tag_text in behavior_keywords:
            boost = BEHAVIOR_WEIGHT * HASHTAG_MULTIPLIER
            score += boost
            hashtag_hits.append(f"#{tag} = behavior (+{round(boost,1)})")
            signal_groups.add("Behavior")

        elif tag_text in seniority_keywords:
            boost = SENIORITY_WEIGHT * HASHTAG_MULTIPLIER
            score += boost
            hashtag_hits.append(f"#{tag} = seniority (+{round(boost,1)})")
            signal_groups.add("Seniority")

        elif tag_text in uae_keywords + mena_keywords:
            boost = GEO_GROUP_BONUS * HASHTAG_MULTIPLIER
            score += boost
            hashtag_hits.append(f"#{tag} = geography (+{round(boost,1)})")
            signal_groups.add("Geography")

    if hashtag_hits:
        breakdown.append("Hashtag signals: " + " | ".join(hashtag_hits))

    location_match = re.search(r"location:\s*([^\n|·]+)", text, re.IGNORECASE)
    if location_match:
        loc = location_match.group(1).lower()
        if any(k in loc for k in uae_keywords + mena_keywords):
            score += 0.5
            breakdown.append("Explicit UAE location (+0.5)")
        elif any(bad in loc for bad in ["london", "singapore", "new york", "usa", "uk", "india"]):
            score -= 1.5 
            breakdown.append("Non-MENA location detected (-1.5)")

    identity_hits = [k for k in identity_keywords if k in text]
    if identity_hits:
        score += IDENTITY_WEIGHT
        breakdown.append(f"Primary identity '{identity_hits[0]}' (+{IDENTITY_WEIGHT})")
        for k in identity_hits[1:]:
            score += IDENTITY_DIMINISHING_WEIGHT
            breakdown.append(f"Additional identity '{k}' (+{IDENTITY_DIMINISHING_WEIGHT})")
        signal_groups.add("Identity")

    behavior_hits = [k for k in behavior_keywords if k in text]
    for k in behavior_hits:
        score += BEHAVIOR_WEIGHT
        breakdown.append(f"Behavior keyword '{k}' (+{BEHAVIOR_WEIGHT})")

    if behavior_hits and "Identity" in signal_groups:
        score += BEHAVIOR_GROUP_BONUS
        breakdown.append(f"Identity + behavior synergy (+{BEHAVIOR_GROUP_BONUS})")
        signal_groups.add("Behavior")

    seniority_hits = [k for k in seniority_keywords if k in text]
    for k in seniority_hits:
        score += SENIORITY_WEIGHT
        breakdown.append(f"Seniority keyword '{k}' (+{SENIORITY_WEIGHT})")

    if seniority_hits:
        score += SENIORITY_GROUP_BONUS
        breakdown.append(f"Seniority group bonus (+{SENIORITY_GROUP_BONUS})")
        signal_groups.add("Seniority")

    # -------------------------
    # Company enrichment (robust)
    # -------------------------

    company_candidates = []

    sentences = re.split(r"[.\n]", text_original)
    for sentence in sentences:
        s = sentence.strip()
        if not s:
            continue

        # HARD BLOCK: multi-company or list-like sentences
        #if re.search(r"\band\b", s.lower()):
        #    continue

        # Possessive senior role → company (TMT Law's Chief Operating Officer)
        company_candidates.extend(re.findall(
            r"\b([A-Z][A-Za-z0-9&.\-]{2,40}(?:\s+[A-Z0-9][A-Za-z0-9&.\-]{1,25}){0,4})['’]s\s+"
            r"(?:Chief|Senior|Managing|Executive|Head|Vice\s+President|VP)\s+"
            r"(?:Operating\s+)?"
            r"(?:Officer|Director|Partner)\b",
            s,
            re.IGNORECASE  # optional, but helps
        ))

        # Role @ Company (LinkedIn-style, case-insensitive company)
        company_candidates.extend(re.findall(
            r"\b(?:head|lead|director|manager|vp|chief)\b[^@]{0,40}"
            r"(?:@| at | for )\s*"
            r"([A-Za-z][A-Za-z0-9 &.\-]{2,50})",
            s,
            re.IGNORECASE
        ))

    # STRONG global founder / C-level patterns (allowed globally)
    company_candidates.extend(re.findall(
        r'\b(?:founder|co[- ]?founder|ceo|cto|cfo|coo|director|partner|President|Chairman|Director|Member)\b'
        r'(?:\s*&\s*\w+)?'
        r'\s+(?:at|@|of)\s+'
        r'([A-Z][A-Za-z0-9 &\.\-]{2,50})',
        text_original,
        re.IGNORECASE
    ))

    # Pattern: | Role, Company | or | Role, Company
    company_candidates.extend(re.findall(
        r'\|\s*(?:CEO|CFO|COO|CTO|Founder|Co-Founder|Managing Director|Founder & CEO)'
        r'(?:\s*[&,]\s*\w+)?'  # Handles "Founder & CEO"
        r',\s+([A-Z][A-Za-z0-9 &\.\-]{2,50})',
        text_original,
        re.IGNORECASE
    ))

    # Angel / investor phrasing (explicit)
    company_candidates.extend(re.findall(
        r"\bAngel Investor\s+(?:at|@)\s+([A-Z][A-Za-z0-9 &.\-]{2,50})",
        text_original,
        re.IGNORECASE
    ))


    # Venture-style phrasing
    company_candidates.extend(re.findall(
        r'\b(?:started|founded)\s+(?:the\s+)?(?:own\s+)?'
        r'(?:venture|company|startup)?\s*(?:of|called)?\s*[‘"\']?'
        r'([A-Z][A-Za-z0-9 &\.\-]{2,50})',
        text_original,
        re.IGNORECASE
    ))

    # -------------------------
    # Cleaning & validation
    # -------------------------

    stop_phrases = [
        "years of", "experience", "worked with", "experience in",
        "services", "solutions", "expansion", "linkedin"
    ]

    cleaned_companies = []
    for comp in company_candidates:
        comp_clean = comp.strip(" .,-·")
        comp_lower = comp_clean.lower()

        # HARD BLOCK: temporal phrases
        if re.search(r"\b(19|20)\d{2}\b", comp_lower):
            continue

        # HARD BLOCK: sentence fragments masquerading as companies
        if comp_lower.startswith(("a ")):
            continue

        if len(comp_clean) < 3:
            continue
        if any(bad in comp_lower for bad in stop_phrases):
            continue
        if re.fullmatch(r"\d+", comp_clean):
            continue

        descriptor_blocks = {
            "career", "experience", "background", "journey", "early",
            "age", "years", "industry", "field", "space",
            "company", "companies", "organization", "organizations",
            "venture", "ventures", "startup", "startups",
            "business", "businesses", "firm", "firms"
        }

        first_words = comp_lower.split()[:3]
        if any(w in descriptor_blocks for w in first_words):
            continue

        cleaned_companies.append(comp_clean)

    # Deduplicate while preserving order
    cleaned_companies = list(dict.fromkeys(cleaned_companies))

    enriched_company = ""
    if cleaned_companies:
        enriched_company = cleaned_companies[0]
        score += 0.3
        breakdown.append(f"Company affiliation: {enriched_company} (+0.3)")


    geo_boost = 0
    if any(k in text for k in uae_keywords + mena_keywords):
        signal_groups.add("Geography")
        geo_boost += GEO_GROUP_BONUS
        
        if "dubai" in text or "abu dhabi" in text:
            geo_boost += 0.3
            breakdown.append("Explicit UAE city mentioned (+0.3)")
        
        breakdown.append(f"Geography signals (+{round(geo_boost, 1)})")
        score += geo_boost

    if "ae.linkedin.com/in" in url:
        score += GEO_GROUP_BONUS
        breakdown.append("UAE LinkedIn domain")
    elif score >= 5.0 and "Geography" not in signal_groups:
        score -= 1.0
        breakdown.append("High score without geography confirmation (-0.5)")
   
    score = max(0.0, min(score, 10.0))

    confidence = "High" if len(signal_groups) >= 3 else "Medium" if len(signal_groups) == 2 else "Low"
    breakdown.insert(0, f"Signal groups fired: {len(signal_groups)}")

    return score, confidence, breakdown, enriched_company

def is_valid_person_name(name):
    if not name:
        return False
    if len(name.split()) < 2:
        return True
    if name.lower() in {"angel investor", "venture capital"}:
        return False
    return True

def extract_name(title):
    for sep in [" - ", " | ", " – ", " — "]:
        if sep in title:
            candidate = title.split(sep)[0].strip()
            return candidate
    return title.strip()

st.subheader("Public Lead Discovery")

query_input = st.text_area(
    "Enter one search query per line",
    height=120,
    placeholder='"angel investor" UAE site:linkedin.com/in'
)

max_results_per_query = st.number_input(
    "Results per query",
    min_value=1,
    max_value=50,
    value=20,
    step=1
)

if st.button("Run Discovery") and query_input.strip():
    queries = [q.strip() for q in query_input.split("\n") if q.strip()]

    with DDGS(timeout=10) as ddgs:
        for query in queries:
            for r in ddgs.text(query, max_results=max_results_per_query, backend="lite"):
                raw_title = r.get("title", "")
                raw_snippet = r.get("body", "")

                title = soft_truncate_ellipsis(raw_title)
                snippet = soft_truncate_ellipsis(raw_snippet)

                url = r.get("href", "")

                if not url:
                    continue

                if any(bad in normalize_url(url) for bad in blocked_urls):
                    continue

                if is_duplicate_url(
                    url,
                    st.session_state.results,
                    title,
                    snippet
                ):
                    continue

                combined = f"{title} {snippet}"
                score, conf, breakdown, enriched_company = score_text(combined, query, url)
                name = extract_name(title)

                if not is_valid_person_name(name):
                    continue

                existing_idx = find_existing_person(url, st.session_state.results)

                if existing_idx is not None:
                    existing = st.session_state.results[existing_idx]

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
                    st.session_state.results.append({
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

EXPECTED_COLUMNS = [
    "Reviewed", "Name", "Title", "Snippet",
    "URL", "Score", "Confidence", "Signals", "Enriched Company"
]

df_first = pd.DataFrame(st.session_state.results)

for col in EXPECTED_COLUMNS:
    if col not in df_first.columns:
        df_first[col] = []

st.dataframe(
    df_first[["Reviewed", "Name", "Title", "Snippet", "Enriched Company", "Score", "Confidence", "Signals", "URL"]],
    use_container_width=True
)

st.subheader("Checklist Helper")

if df_first.empty:
    st.info("No rows available yet.")
else:
    selected_index = st.number_input(
        "Row number to copy (0-based index)",
        min_value=0,
        max_value=len(df_first) - 1,
        value=0,
        step=1
    )

    row = df_first.iloc[selected_index]

    checklist_text = f"""
-----------------------------------------------
RAW TITLE TEXT (VERBATIM):
{row.get('Title', '')}

RAW SNIPPET TEXT (VERBATIM):
{row.get('Snippet', '')}

SEARCH MODE (QUOTED / UNQUOTED):

QUERY USED:
(manual)

NAME COMMONALITY (RARE / MODERATE / VERY COMMON, multiple linkedin profile with similar name, chance of false positive in second pass):

FINAL SCORE:
{row.get('Score', '')}

SYSTEM CONFIDENCE (LOW / MEDIUM / HIGH, should they move on to second pass?):
{row.get('Confidence', '')}

TOP CONTRIBUTORS (exact keywords or signals that boosted score):
{row.get('Signals', '')}

YOUR VERDICT (REJECT / SECOND PASS OK / CLEARLY GOOD):

SNIPPET ALONE FELT SUFFICIENT TO DECIDE? (YES / NO):

IF SCORE WERE 0.2 LOWER, WOULD YOU STILL KEEP IT? (YES / NO):

DID YOU FEEL THE NEED TO CLICK A PROFILE? (YES / NO):

IF YES, WHY? (ambiguity / role unclear / geography unclear / seniority unclear / other):

FALSE-POSITIVE RISK (LOW / MEDIUM / HIGH):

MISSING-BUT-OBVIOUS SIGNAL (OPTIONAL):

EDGE-CASE TYPE (if any):
(common name / inflated title / geography mismatch / keyword bait / unclear investor type / other):

NOTES (OPTIONAL, is role explicit and suggest influence capital or decision authority, any signals here the person invests or allocates capital or advises on investments, anything unique that stands out):
"""

    st.text_area(
        "Copy into your checklist",
        checklist_text,
        height=500
    )
