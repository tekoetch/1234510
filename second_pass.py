import re
from first_pass import (
    identity_keywords, 
    behavior_keywords, 
    uae_keywords, 
    mena_keywords
)

# --- CONFIGURATION ---

# Domains that are pure noise and should result in a 0 score
NOISE_DOMAINS = [
    "wikipedia.org", "saatchiart.com", "researchgate.net", 
    "academia.edu", "sciprofiles.com", "datapile.co"
]

# Domains that provide "Contact Info Available" signals (Bonus)
BONUS_DOMAINS = ["theorg.com", "rocketreach.co", "crunchbase.com", "pitchbook.com"]

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

    # Priority 2: Name + Identity Keyword (e.g. "John Doe" "Angel Investor")
    if anchors["identity"]:
        queries.append(f'{quoted_name} "{anchors["identity"][0]}"')
    
    # Priority 3: Name + Extracted Company + "Investor"
    elif anchors["company"]:
        queries.append(f'{quoted_name} "{anchors["company"][0]}" investor')
    
    # Priority 4: Name + Behavior (e.g. "John Doe" "Portfolio")
    elif anchors["behavior"]:
        queries.append(f'{quoted_name} "{anchors["behavior"][0]}"')

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
    Scores verification results using your specific weights.
    """
    t = text.lower()
    score = 0
    breakdown = []
    
    # --- BLOCKING LOGIC ---
    
    if any(d in url for d in NOISE_DOMAINS):
        return 0, ["Noise domain"], False
    
    if "linkedin.com/pub/dir" in url:
        return 0, ["LinkedIn directory page ignored"], False

    if "linkedin.com/in" in url:
        return 0, ["LinkedIn profile ignored in second pass"], False


    # --- SCORING LOGIC ---

    # 1. Identity Confirmation (+1.5)
    if any(k in t for k in identity_keywords):
        if not state["identity_confirmed"]:
            score += 1.5
            breakdown.append("Confirmed investor identity (+1.5)")
            state["identity_confirmed"] = True

    # 2. Behavior Signals (+0.5)
    if any(k in t for k in behavior_keywords):
        score += 0.5
        breakdown.append("Investment behavior language (+0.5)")

    # 3. Geography Verification (+0.3)
    if any(k in t for k in uae_keywords + mena_keywords):
        if state["geo_hits"] < 2 and state["identity_confirmed"]:
            score += 0.3
            breakdown.append("Supporting geography signal (+0.3)")
            state["geo_hits"] += 1

    # 4. Bonus Domains / Contact Info (+0.4)
    for d in BONUS_DOMAINS:
        if d in url and d not in state["domain_hits"]:
            score += 0.4
            breakdown.append(f"External confirmation via {d} (+0.4)")
            breakdown.append("Public contact information likely available")
            state["domain_hits"].add(d)

    return min(score, 5.0), breakdown, state["identity_confirmed"]
