import re

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
    "founder", "co-founder", "ceo", "incubator", "angel",
    "vc investor"
]

behavior_keywords = [
    "invested in", "investing in", "portfolio", "Series A",
    "seed", "pre-seed", "early-stage", "funding", "summit",
    "venture capital", "private equity", "real estate",
    "fundraising", "investment portfolio", "wealth funds",
    "property management", "dedicated portfolio", "active"
]

seniority_keywords = [
    "partner", "managing director", "chairman",
    "board member", "advisor", "advisory", "chair",
]

filter_list = [
    "entrepreneur", "fractional", "chief executive officer",
    "self-employed", "self employed", "angel investing", "cfo",
    "managing", "own", "head of sales", "chief operating officer",
    "strategic finance", "investment professional", "director",
    "chief investment officer", "executive"
]

uae_keywords = ["uae", "dubai", "abu dhabi", "emirates"]
mena_keywords = ["mena", "middle east", "gulf", "gcc"]

NON_MENA_HUBS = [
    "india", "pakistan", "bangalore", "ahmedabad", "mumbai", "delhi", "pune",
    "singapore", "usa", "united states", "uk", "united kingdom", "london", 
    "san francisco", "new york", "nyc", "canada", "australia", "berlin", "europe"
]

def contains_whole_word(text, word):
    return re.search(r'\b' + re.escape(word) + r'\b', text) is not None

def contains_bucket_keyword(text):
    text_lower = text.lower()

    for bucket in [identity_keywords, filter_list]:
        for keyword in bucket:
            if contains_whole_word(text_lower, keyword.lower()):
                return True

    return False


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
    #if location_match:
     #   loc = location_match.group(1)
      #  if any(k in loc for k in uae_keywords + mena_keywords):
       #     score += 0.5
        #    breakdown.append("Explicit UAE location (+0.5)")
        #elif any(bad in loc for bad in ["Singapore", "New York City", "United States", "UK", "London", "India", "Ahmedabad", "Mumbai"]):
         #   score -= 1.5 
          #  breakdown.append("Non-MENA location detected (-1.5)")

    if location_match:
        loc_text = location_match.group(1).strip().lower()
        
        # Check if it's a GOOD location first
        is_uae_mena = any(k in loc_text for k in uae_keywords + mena_keywords)
        
        if is_uae_mena:
            score += 1.0  # Increased boost for confirmed target location
            breakdown.append(f"Confirmed MENA Location: {loc_text} (+1.0)")
        else:
            # Check if it's explicitly in our known "Bad Hubs" list
            is_bad_hub = any(bad in loc_text for bad in NON_MENA_HUBS)
            
            if is_bad_hub:
                score -= 4.0  # Heavy penalty to kill the lead
                breakdown.append(f"Non-MENA Country ({loc_text}) (-4.0)")
            else:
                # If a location is mentioned but it's NOT MENA, it's suspicious
                score -= 2.0
                breakdown.append(f"Suspicious Location: {loc_text} (-2.0)") 

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
            re.IGNORECASE
        ))

        # Role @ Company (LinkedIn-style, case-insensitive company)
        company_candidates.extend(re.findall(
            r"\b(?:head|lead|director|manager|vp|chief|growth|role|partner|ceo|cio)\b[^@]{0,40}"
            r"(?:@| at | for )\s*"
            r"([A-Za-z][A-Za-z0-9 &.\-]{2,50})",
            s,
            re.IGNORECASE
        ))

        # Title format: "Name - Company | LinkedIn" or "Name @ Company"
        headline_matches = re.findall(
            r'^[^\n\-@]{2,100}\s*[-@]\s*(.*?)\s*(?:\|\s*LinkedIn)?(?:\||$)',
            text_original,
            re.MULTILINE
        )

        cleaned_headlines = []

        for item in headline_matches:
            item = item.strip()
            item = re.sub(r'\s{2,}', ' ', item)  # collapse spaces

            # Remove emoji and weird symbols
            item = re.sub(r'[^\w\s\-\&\.\,]', '', item)

            cleaned_headlines.append(item)

        processed_candidates = []

        for item in cleaned_headlines:

            # If headline has pipes, take first segment only
            if "|" in item:
                item = item.split("|")[0].strip()

            # If multiple dash segments, take LAST segment (often company)
            if " - " in item:
                segments = item.split(" - ")
                item = segments[-1].strip()

            processed_candidates.append(item)

        for candidate in processed_candidates:
            if not contains_bucket_keyword(candidate):
                if len(candidate.strip()) > 2:
                    company_candidates.append(candidate.strip())
    
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

        if re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b", comp_lower):
            continue

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

    # FINAL GLOBAL FILTER PASS
    filtered_companies = []

    for candidate in company_candidates:
        candidate_clean = candidate.strip()

        if len(candidate_clean) <= 2:
            continue

        if contains_bucket_keyword(candidate_clean):
            continue

        filtered_companies.append(candidate_clean)

    company_candidates = filtered_companies
        

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
        breakdown.append("UAE LinkedIn domain (+0.6)")
    elif score >= 5.0 and "Geography" not in signal_groups:
        score -= 1.3 #changed from 1.1 because Matt H. got 5 with Location United States
        breakdown.append("High score without geography confirmation (-1.3)")

    if any(dom in url for dom in ["in.linkedin.com/in", "br.linkedin.com/in", "pk.linkedin.com/in"]):
        score -= 0.3
        breakdown.append("Outside Region LinkedIn country domain (-0.3)")
    
   
    score = max(0.0, min(score, 10.0))

    confidence = "High" if len(signal_groups) >= 3 else "Medium" if len(signal_groups) == 2 else "Low"
    breakdown.insert(0, f"Signal groups fired: {len(signal_groups)}")

    return score, confidence, breakdown, enriched_company
