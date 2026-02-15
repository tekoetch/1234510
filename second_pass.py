import re
from first_pass import (
    identity_keywords, 
    behavior_keywords, 
    uae_keywords, 
    mena_keywords,
    seniority_keywords
)

# --- CONFIGURATION ---

# Domains that are pure noise and should result in a 0 score
NOISE_DOMAINS = [
    "wikipedia.org", "saatchiart.com", "researchgate.net", 
    "academia.edu", "sciprofiles.com", "datapile.co",
    "dubaiangelinvestors.me", "rasmal.com",
    "new-delhi.startups-list.com", "appriffy.com",
    "ycombinator.com", "kr-asia.com", "www.goswirl.ai",
    "www.science.gov", "cryptonews.com", "blog.founderfirst.org",
    "abcnews.go.com", "www.wamda.com", "www.startupresearcher.com",
    "www.cbnme.com", "www.standard.co.uk", "diamondclubwestcoast.com",
    "www.theguardian.com", "cointelegraph.com", "www.menaangelinvestor.com",
    "finanshels.com", "www.easmea.com", "www.gulftalent.com", "www.tahawultech.com",
    "www.ainalemirate.com", "www.globalstartups.club", "ticker.finology.in",
    "www.pacermonitor.com", "blog.teamwave.com", "finanshels.com", "www.bloomberg.com",
    "www.folk.app", "/blog", "/news", "/articles", "/news-events"
]

# Domains that provide "Contact Info Available" signals (Bonus)
BONUS_DOMAINS = ["theorg.com", "rocketreach.co", "crunchbase.com", "pitchbook.com", 
                 "zoominfo.com", "raizer.app", "xing.com", "people.equilar.com",
                 "tridentconsultingme.com", "contactout.com"
                 ]

QUERY_BLOCKLIST = {"partner", "ceo", "co-founder", "founder"}

def extract_anchors(text):
    """
    Extracts keywords from the First Pass snippet to build targeted queries.
    """
    anchors = {"identity": [], "behavior": [], "company": []}
    t = text.lower()

    # 1. Identity Anchors (e.g. Angel Investor)
    for kw in identity_keywords:
        if kw in t and kw not in QUERY_BLOCKLIST:
            anchors["identity"].append(kw)

    # 2. Behavior Anchors (e.g. "invested in")
    for kw in behavior_keywords:
        if kw in t:
            anchors["behavior"].append(kw)

    # 3. Company Anchors (Regex extraction)
    # Looks for "at [Company]" or "CEO of [Company]"
    companies = re.findall(r"\b(?:at|of|with)\s+([A-Z][A-Za-z0-9 &]{2,20})", text)
    if not companies:
        # Fallback: Try to grab the Enriched Company from the row data if passed
        pass 
    
    for c in companies:
        if len(c) > 3 and c.lower() not in {"the", "and", "investment"}:
            anchors["company"].append(c.strip())

    return anchors

def build_second_pass_queries(name, anchors, enriched_company=""):
    """
    Constructs 2 targeted queries.
    """
    quoted_name = f'"{name}"'
    queries = []

    # Priority 1: Name + Enriched Company (Strongest)
    if enriched_company:
         queries.append(f'{quoted_name} "{enriched_company}"')
    
    # Priority 3: Name + Extracted Company + "Investor"
    elif anchors["company"]:
        queries.append(f'{quoted_name} "{anchors["company"][0]}" investor')
    
    # Priority 4: Name + Behavior (e.g. "John Doe" "Portfolio")
    elif anchors["behavior"]:
        queries.append(f'{quoted_name} "{anchors["behavior"][0]}"')

    # Priority 2 (temporary at 4): Name + Identity Keyword (e.g. "John Doe" "Angel Investor")
    if anchors["identity"]:
        queries.append(f'{quoted_name} "{anchors["identity"][0]}"')    

    # Always ensure we have at least one query with region
    final_queries = []
    for q in queries:
        final_queries.append(f'{q} UAE')
        
    # Fallback if no anchors found
    if not final_queries:
        final_queries.append(f'{quoted_name} UAE investment')

    return list(dict.fromkeys(final_queries))[:2]


def score_second_pass(text, url, state):
    """
    Scores verification results using the new 1-10 Scale.
    """
    t = text.lower()
    # Block Google's "Missing:" and "Show results with:" artifacts
    if "missing:" in t or "show results with:" in t:
        return 0, ["Search artifact ignored"], False
    score = 0
    breakdown = []
    
    # --- BLOCKING LOGIC ---
    
    if any(d in url for d in NOISE_DOMAINS):
        return 0, ["Noise domain"], False
    
    if "linkedin.com/pub/dir" in url:
        return 0, ["LinkedIn directory page ignored"], False

    if "linkedin.com/in" in url:
        # Check if this LinkedIn profile adds NEW info compared to first pass
        new_info = False
        # We check if any significant keywords exist here that we are looking for
        for k in identity_keywords + behavior_keywords + seniority_keywords + uae_keywords + mena_keywords:
            if k in t:
                new_info = True
                break
        
        if not new_info:
            return 0, ["LinkedIn adds no new information"], False
        
    if "linkedin.com" in url:
        if state["linkedin_hits"] >= 4:
            return 0, ["LinkedIn limit reached"], False
        state["linkedin_hits"] += 1

    if "tracxn.com/d/people/" in url:
        slug = url.split("/d/people/")[-1].split("/")[0]
        name_slug = slug.replace("-", " ")

        if state.get("expected_name"):
            if state["expected_name"].lower() not in name_slug.lower():
                return 0, ["Tracxn non-matching person ignored"], False

    # --- SCORING LOGIC (1-10 Scale) ---

        # 4. Bonus Domains / Contact Info (+1.0)
    for d in BONUS_DOMAINS:
        if d in url and d not in state["domain_hits"]:
            score += 1.0
            breakdown.append(f"External confirmation via {d} (+1.0)")
            breakdown.append("Public contact information likely available")
            state["domain_hits"].add(d)

    # 1. Identity Confirmation (+4.0) - BIG BOOST
    # If we find "Angel Investor" in a second source, that's nearly a pass.
    if any(k in t for k in identity_keywords):
        if not state["identity_confirmed"]:
            score += 4.0
            breakdown.append("Confirmed investor identity (+4.0)")
            state["identity_confirmed"] = True

    # 2. Behavior Signals (+3.0) - BIG BOOST
    if any(k in t for k in behavior_keywords):
        score += 3.0
        breakdown.append("Investment behavior language (+3.0)")

    if any(k in t for k in seniority_keywords):
        score += 1.0
        breakdown.append("Seniority language (+1.0)")

    # 3. Geography Verification (+3.0) - BIG BOOST
    if any(k in t for k in uae_keywords + mena_keywords):
        if state["geo_hits"] < 2:
            # We allow up to 2 hits for geo to accumulate confidence
            score += 1.5 
            breakdown.append("Supporting geography signal (+1.5)")
            state["geo_hits"] += 1

    # Cap score at 10.0
    final_score = min(score, 10.0)
    
    return final_score, breakdown, state["identity_confirmed"]
