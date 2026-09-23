"""
analyzer.py — Linguistic analysis for TruthLens

Provides:
  clean_text()          — normalise text for embedding
  detect_topic()        — classify into topic buckets
  detect_location()     — geo-scope detection
  detect_temporal()     — today / yesterday / tomorrow / week / month / recent / any
  check_negation()      — is the query a debunk / fact-check request?
  get_predicates()      — extract event verbs
  get_linguistic_score() — combined dict used by predictor
"""

import re
from datetime import datetime, timedelta

# ── Keyword Banks ─────────────────────────────────────────────
SOURCE_WORDS = [
    'according to', 'reported by', 'said', 'told', 'announced', 'confirmed',
    'stated', 'officials said', 'spokesperson', 'in a statement',
    'associated press', 'reuters', 'sources say', 'government said',
    'published by', 'as per', 'citing', 'quoting',
]

SENSATIONAL_WORDS = [
    'shocking', 'bombshell', 'explosive', 'incredible', 'mind-blowing',
    'what really happened', 'conspiracy', 'hoax', 'cover-up', 'secret',
    "they don't want you to know", 'wake up', 'exposed', 'breaking',
    'you wont believe', 'truth revealed', 'hidden agenda',
]

FAKE_HARD_PHRASES = [
    'mind control', 'microchip vaccine', 'deep state', 'flat earth',
    'crisis actor', 'plandemic', 'chemtrail', 'illuminati', 'new world order',
    'reptilian', 'george soros controls', 'bill gates microchip',
    'scamdemic', 'globalist agenda', '5g causes', 'vaccines cause autism',
]

MAJOR_EVENT_VERBS = [
    'died', 'death', 'killed', 'arrested', 'won', 'lost', 'resigned',
    'hospitalized', 'guilty', 'innocent', 'banned', 'launched', 'crashed',
    'elected', 'fired', 'promoted', 'merged', 'acquired', 'collapsed',
    'attacked', 'sentenced', 'charged', 'indicted',
]

# ── Topic keywords ────────────────────────────────────────────
TOPIC_KEYWORDS: dict[str, list[str]] = {
    'weather': [
        'weather', 'rain', 'storm', 'forecast', 'imd', 'celsius',
        'flood', 'cyclone', 'monsoon', 'temperature', 'humidity',
        'drought', 'heatwave', 'lightning', 'thunderstorm', 'cloudy',
        'rainfall', 'precipitation', 'wind', 'alert', 'warning',
        'sunny', 'overcast', 'mist', 'fog', 'cold wave', 'heat wave',
        'yellow alert', 'orange alert', 'red alert', 'imd forecast',
    ],
    'sports': [
        'cricket', 'football', 'ipl', 'score', 'team', 'match',
        'player', 'tournament', 'fifa', 'olympic', 'champion',
        'test match', 'odi', 't20', 'batting', 'bowling', 'goal',
        'league', 'cup', 'trophy', 'series', 'innings', 'wicket',
        'kabaddi', 'hockey', 'badminton', 'tennis',
    ],
    'telangana': [
        'telangana', 'hyderabad', 'ghmc', 'kcr', 'ktr', 'revanth',
        'warangal', 'nizamabad', 'karimnagar', 'khammam', 'brs',
        'trs', 'secunderabad', 'charminar', 'hussain sagar',
        'cyberabad', 'kukatpally', 'lb nagar', 'hanuman junction',
        'jubilee hills', 'banjara hills', 'gachibowli', 'hitec city',
        'ameerpet', 'dilsukhnagar', 'uppal', 'sainikpuri',
        'v6', 'tv9 telugu', 'sakshi', 'abn', 'ntv telugu',
    ],
    'politics': [
        'election', 'government', 'minister', 'vote', 'policy',
        'bjp', 'congress', 'parliament', 'modi', 'rahul',
        'assembly', 'loksabha', 'rajyasabha', 'governor', 'cm',
        'opposition', 'party', 'candidate', 'manifesto', 'rally',
        'corruption', 'scam', 'protest', 'bypolls', 'mla', 'mp',
    ],
    'health': [
        'health', 'vaccine', 'covid', 'hospital', 'doctor', 'virus',
        'disease', 'medicine', 'treatment', 'surgery', 'patient',
        'pandemic', 'epidemic', 'who', 'icmr', 'aiims',
        'prescription', 'drug', 'clinical', 'symptoms', 'mpox',
    ],
    'crime': [
        'murder', 'robbery', 'theft', 'rape', 'assault', 'police',
        'arrested', 'fir', 'case', 'court', 'judge', 'verdict',
        'accused', 'criminal', 'gang', 'kidnap', 'drug bust',
        'encounter', 'bail', 'chargesheet',
    ],
    'business': [
        'stock', 'market', 'economy', 'gdp', 'inflation', 'rbi',
        'bank', 'rupee', 'dollar', 'sensex', 'nifty', 'company',
        'startup', 'merger', 'acquisition', 'profit', 'loss',
        'budget', 'tax', 'gst', 'revenue', 'investment', 'sebi',
    ],
    'technology': [
        'ai', 'artificial intelligence', 'robot', 'software',
        'hardware', 'app', 'mobile', 'internet', 'cyber', 'hack',
        'chatgpt', 'smartphone', 'tesla', 'elon', 'space',
        'satellite', 'isro', 'nasa', 'launch', 'orbit', '5g',
    ],
    'world': [
        'usa', 'america', 'china', 'russia', 'ukraine', 'war',
        'un', 'nato', 'europe', 'iran', 'israel', 'pakistan',
        'afghanistan', 'geopolitics', 'sanctions', 'diplomacy',
        'g20', 'g7', 'imf', 'world bank',
    ],
}

# ── Geography ─────────────────────────────────────────────────
GEOGRAPHY_KEYWORDS: dict[str, list[str]] = {
    'hyderabad': [
        'hyderabad', 'hyd', 'secunderabad', 'cyberabad',
        'ghmc', 'charminar', 'hussain sagar', 'jubilee hills',
        'banjara hills', 'hitec city', 'gachibowli', 'kukatpally',
        'lb nagar', 'dilsukhnagar', 'uppal', 'ameerpet',
        'madhapur', 'kondapur', 'miyapur', 'kompally',
        'shamsabad', 'shamshabad', 'koheda', 'metro', 'metro rail',
        'fruit market', 'patancheru', 'nagole', 'malkajgiri',
    ],
    'telangana': [
        'telangana', 'ts', 'warangal', 'nizamabad', 'karimnagar',
        'khammam', 'nalgonda', 'mahabubnagar', 'adilabad',
        'sangareddy', 'medak', 'siddipet', 'suryapet',
        'mancherial', 'jagtial', 'rajanna', 'nagarkurnool',
        'rangareddy', 'medchal', 'yadadri', 'bhadradri',
    ],
    'mumbai': [
        'mumbai', 'bombay', 'maharashtra', 'pune', 'thane',
        'navi mumbai', 'bmc', 'nashik', 'aurangabad',
    ],
    'delhi': [
        'delhi', 'ncr', 'new delhi', 'noida', 'gurgaon',
        'faridabad', 'ghaziabad', 'mcd', 'ndmc',
    ],
    'bangalore': ['bangalore', 'bengaluru', 'karnataka', 'mysuru', 'bbmp'],
    'chennai':   ['chennai', 'tamil nadu', 'madras', 'coimbatore', 'madurai'],
    'kolkata':   ['kolkata', 'west bengal', 'calcutta', 'howrah'],
    'india':     ['india', 'indian', 'bharat', 'modi', 'new delhi'],
}

# ── Temporal markers (expanded) ───────────────────────────────
_TODAY_WORDS    = [
    'today', 'now', 'latest', 'just', 'breaking', 'current', 'live',
    'right now', 'this morning', 'this evening', 'this afternoon',
    'tonight', 'aaj', 'abhi', 'इस वक्त',
]
_TOMORROW_WORDS = [
    'tomorrow', 'kal', 'next day', 'day after', 'coming day',
    'tomorrow morning', 'tomorrow evening', 'tomorrow night',
]
_YEST_WORDS     = [
    'yesterday', 'last night', 'last evening', 'kal raat',
    'previous day', 'day before',
]
_RECENT_WORDS   = [
    'this week', 'recently', 'last week', 'past few days',
    'few hours ago', 'past 24 hours', 'past 48 hours',
    'is week', 'this month', 'last month',
]
_WEEK_WORDS     = [
    'monday', 'tuesday', 'wednesday', 'thursday', 'friday',
    'saturday', 'sunday', 'this week', 'next week', 'last week',
    'weekday', 'weekend', 'weekly',
]
_MONTH_WORDS    = [
    'january', 'february', 'march', 'april', 'may', 'june',
    'july', 'august', 'september', 'october', 'november', 'december',
    'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
    'this month', 'next month', 'last month', 'monthly',
]

# ── Debunk phrases ────────────────────────────────────────────
_DEBUNK_PHRASES = [
    'is this fake', 'is this true', 'is this real',
    'fact check', 'is it true that', 'rumour that',
    'hoax about', 'debunked', 'this is false',
    'misinformation about', 'is it fake',
]


# ── Public API ────────────────────────────────────────────────

# ── Conversational prefixes and Telugu Translits ─────────────────────
CONVERSATIONAL_PREFIXES = [
    r'^is it true that',
    r'^can you check if',
    r'^can you verify if',
    r'^please check if',
    r'^verify whether',
    r'^do you know if',
    r'^i heard that',
    r'^rumor says that',
    r'^rumour says that',
    r'^news about',
    r'^fact check',
    r'^fact-check',
    r'^debunk',
    r'^hoax of',
    r'^is this fake',
    r'^is this true',
    r'^is it fake that',
    r'^tell me if',
]

TELUGU_TRANSLIT_MAP = {
    'varsham': 'వర్షం',
    'varshalu': 'వర్షాలు',
    'vana': 'వాన',
    'vanalu': 'వానలు',
    'kcr': 'కేసీఆర్',
    'ktr': 'కేటీఆర్',
    'revanth': 'రేవంత్',
    'revanth reddy': 'రేవంత్ రెడ్డి',
    'jagan': 'జగన్',
    'chandrababu': 'చంద్రబాబు',
    'cbn': 'చంద్రబాబు',
    'naidu': 'నాయుడు',
    'pawan': 'పవన్',
    'kalyan': 'కళ్యాణ్',
    'bjp': 'బీజేపీ',
    'congress': 'కాంగ్రెస్',
    'brs': 'బీఆర్ఎస్',
    'hyderabad': 'హైదరాబాద్',
    'telangana': 'తెలంగాణ',
    'andhra': 'ఆంధ్ర',
    'pradesh': 'ప్రదేశ్',
    'amaravati': 'అమరావతి',
    'secunderabad': 'సికింద్రాబాద్',
    'selavulu': 'సెలవులు',
    'selavu': 'సెలవు',
    'badi': 'బడి',
    'patashala': 'పాఠశాల',
    'pramadam': 'ప్రమాదం',
    'accident': 'ప్రమాదం',
    'chani': 'చని',
    'chanipoyaru': 'చనిపోయారు',
    'maranam': 'మరణం',
    'arrest': 'అరెస్ట్',
    'donga': 'దొంగ',
    'dongatanam': 'దొంగతనం',
    'elections': 'ఎన్నికలు',
    'rajakeeyalu': 'రాజకీయాలు',
    'dhara': 'ధర',
    'dharalu': 'ధరలు',
    'pelli': 'పెళ్లి',
    'vivaham': 'వివాహం',
}


def strip_conversational_noise(text: str) -> str:
    """Strip conversational wrappers at the start of a user query."""
    txt = text.strip()
    altered = True
    while altered:
        altered = False
        txt_lower = txt.lower()
        for pattern in CONVERSATIONAL_PREFIXES:
            match = re.match(pattern, txt_lower)
            if match:
                txt = txt[match.end():].strip()
                # Strip leading connectors like "that", "whether", "if", "about", punctuation
                txt = re.sub(r'^(that|whether|if|about|is|a|an|the|:|,\s*)+', '', txt, flags=re.I).strip()
                txt_lower = txt.lower()
                altered = True
                break
    return txt


def expand_telugu_query(text: str) -> str:
    """Detect English transliterated Telugu words and append their Telugu script equivalent."""
    words = re.findall(r'[a-zA-Z]+', text.lower())
    expansions = []
    
    # Check multi-word keys first
    text_lower = text.lower()
    for key, val in TELUGU_TRANSLIT_MAP.items():
        if ' ' in key and key in text_lower:
            expansions.append(val)
            
    # Check single-word keys
    for w in words:
        if w in TELUGU_TRANSLIT_MAP and ' ' not in w:
            val = TELUGU_TRANSLIT_MAP[w]
            if val not in expansions:
                expansions.append(val)
                
    if expansions:
        return text + " " + " ".join(expansions)
    return text


def correct_typos(text: str) -> str:
    """Correct minor typos in the query words using fuzzy matching against keyword banks."""
    words = text.split()
    corrected = []
    
    # Collect all words from keyword banks
    all_kws = []
    for topic, kws in TOPIC_KEYWORDS.items():
        for kw in kws:
            all_kws.extend(kw.split())
    for loc, kws in GEOGRAPHY_KEYWORDS.items():
        for kw in kws:
            all_kws.extend(kw.split())
            
    # Add other common terms
    all_kws.extend([
        'market', 'query', 'verify', 'verifying', 'news', 'school', 
        'holidays', 'announcement', 'announced', 'breaking', 'latest',
        'alert', 'heavy', 'rain', 'weather', 'metro', 'stadium', 'today'
    ])
    all_kws = list(set([k.lower() for k in all_kws]))
    
    import difflib
    for w in words:
        w_clean = re.sub(r'^[^\w]*|[^\w]*$', '', w).lower()
        if not w_clean or len(w_clean) < 4:
            corrected.append(w)
            continue
            
        if w_clean in all_kws:
            corrected.append(w)
            continue
            
        # Look for close matches
        matches = difflib.get_close_matches(w_clean, all_kws, n=1, cutoff=0.78)
        if matches:
            best_match = matches[0]
            if w_clean and w[0].isupper():
                best_match = best_match.capitalize()
            w_prefix = re.match(r'^[^\w]*', w).group(0)
            w_suffix = re.search(r'[^\w]*$', w).group(0)
            corrected.append(w_prefix + best_match + w_suffix)
        else:
            corrected.append(w)
            
    return " ".join(corrected)


def match_location(text: str, query_loc: str) -> bool:
    """Return True if text contains any sub-region or geo keyword associated with query_loc."""
    if query_loc == 'global':
        return True
    txt = text.lower()
    kws = GEOGRAPHY_KEYWORDS.get(query_loc, [query_loc])
    for kw in kws:
        pattern = r'\b' + re.escape(kw) + r'\b'
        if re.search(pattern, txt):
            return True
    return False


# ── Public API ────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Normalise text for embedding: remove noise, correct typos, expand transliterated Telugu, strip URLs, keep Unicode words."""
    text = str(text)
    text = strip_conversational_noise(text)
    text = correct_typos(text)
    text = expand_telugu_query(text)
    text = text.lower()
    text = re.sub(r'https?://\S+|www\.\S+', '', text)
    # \w preserves Unicode characters like Telugu script, unlike standard a-zA-Z
    text = re.sub(r'[^\w\s]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def detect_topic(text: str) -> str:
    """Return highest-scoring topic label, or 'general' using word boundary matching."""
    txt = text.lower()
    scores = {}
    for topic, kws in TOPIC_KEYWORDS.items():
        score = 0
        for kw in kws:
            pattern = r'\b' + re.escape(kw) + r'\b'
            if re.search(pattern, txt):
                score += 1
        scores[topic] = score
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else 'general'


def detect_location(text: str) -> str:
    """Return primary geographic scope, or 'global' using word boundary matching."""
    txt = text.lower()
    scores = {}
    for loc, kws in GEOGRAPHY_KEYWORDS.items():
        score = 0
        for kw in kws:
            pattern = r'\b' + re.escape(kw) + r'\b'
            if re.search(pattern, txt):
                score += 1
        scores[loc] = score
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else 'global'


def detect_temporal(text: str) -> str:
    """
    Classify query time-scope as:
      'today' | 'tomorrow' | 'yesterday' | 'week' | 'month' | 'recent' | 'any'
    Order matters — more specific checks first, utilizing word boundary matching.
    """
    txt = text.lower()
    if any(re.search(r'\b' + re.escape(k) + r'\b', txt) for k in _TODAY_WORDS):     return 'today'
    if any(re.search(r'\b' + re.escape(k) + r'\b', txt) for k in _TOMORROW_WORDS):  return 'tomorrow'
    if any(re.search(r'\b' + re.escape(k) + r'\b', txt) for k in _YEST_WORDS):      return 'yesterday'
    if any(re.search(r'\b' + re.escape(k) + r'\b', txt) for k in _MONTH_WORDS):     return 'month'
    if any(re.search(r'\b' + re.escape(k) + r'\b', txt) for k in _WEEK_WORDS):      return 'week'
    if any(re.search(r'\b' + re.escape(k) + r'\b', txt) for k in _RECENT_WORDS):    return 'recent'
    return 'any'


def temporal_label(temporality: str) -> str:
    """Human-friendly label for a temporal category."""
    now = datetime.now()
    labels = {
        'today':     f"today ({now.strftime('%A, %d %b %Y')})",
        'tomorrow':  f"tomorrow ({(now + timedelta(days=1)).strftime('%A, %d %b %Y')})",
        'yesterday': f"yesterday ({(now - timedelta(days=1)).strftime('%A, %d %b %Y')})",
        'week':      f"this week (week of {now.strftime('%d %b %Y')})",
        'month':     f"this month ({now.strftime('%B %Y')})",
        'recent':    'recent (last 48h)',
        'any':       'any time',
    }
    return labels.get(temporality, temporality)


def check_negation(text: str) -> bool:
    """Return True if the query is itself a debunking / fact-check request with word boundary check."""
    tl = text.lower()
    return any(re.search(r'\b' + re.escape(p) + r'\b', tl) for p in _DEBUNK_PHRASES)


def get_predicates(text: str) -> list[str]:
    """Extract event-verb predicates from the query with word boundary check."""
    tl = text.lower()
    return [v for v in MAJOR_EVENT_VERBS if re.search(r'\b' + re.escape(v) + r'\b', tl)]


def get_linguistic_score(text: str) -> dict:
    """
    Returns:
        topic          : str
        hard_hit       : bool
        temporality    : str
    """
    tl        = text.lower()
    hard_hit  = any(re.search(r'\b' + re.escape(p) + r'\b', tl) for p in FAKE_HARD_PHRASES)

    return {
        'topic':          detect_topic(text),
        'hard_hit':       hard_hit,
        'temporality':    detect_temporal(text),
    }


# ── Event Claim Verification Helpers ─────────────────────────────────

EVENT_VERB_GROUPS = {
    'death': {'die', 'dies', 'died', 'death', 'dead', 'dying', 'killed', 'kill', 'kills', 'assassinated', 'assassinate', 'passed away', 'demise', 'fatal'},
    'arrest': {'arrest', 'arrested', 'arrests', 'arresting', 'jail', 'jailed', 'police', 'custody', 'charge', 'charged', 'charges', 'indicted', 'indictment', 'sued', 'lawsuit', 'guilty', 'convicted', 'sentenced'},
    'win_lose': {'won', 'wins', 'win', 'winning', 'defeat', 'defeats', 'defeated', 'lost', 'loses', 'lose', 'losing', 'victory', 'triumph', 'champion', 'champions'},
    'resign_fire': {'resign', 'resigns', 'resigned', 'resigning', 'resignation', 'fired', 'fire', 'firing', 'dismissed', 'dismiss', 'step down', 'steps down', 'stepped down'},
    'health': {'hospital', 'hospitalized', 'hospitalization', 'ill', 'illness', 'sick', 'admitted', 'condition', 'treatment', 'cancer', 'disease', 'surgery', 'icu'},
    'marriage': {'married', 'marry', 'marries', 'marriage', 'wedding', 'engaged', 'engagement', 'divorce', 'divorced'},
    'crash': {'crash', 'crashed', 'crashes', 'accident', 'accidents', 'collision', 'collide', 'collided'},
}

# Stems used to robustly identify query event groups (even with typos or wrong grammar tenses)
EVENT_VERB_STEMS = {
    'death': ['die', 'dead', 'dying', 'kill', 'assassin', 'pass away', 'demise', 'fatal'],
    'arrest': ['arrest', 'jail', 'polic', 'custody', 'charg', 'indict', 'sue', 'lawsuit', 'guilt', 'convict', 'sentenc'],
    'win_lose': ['win', 'won', 'defeat', 'lost', 'lose', 'losing', 'victor', 'triumph', 'champion'],
    'resign_fire': ['resign', 'fire', 'firing', 'dismiss', 'step down', 'stepped down'],
    'health': ['hospital', 'ill', 'sick', 'admit', 'cancer', 'disease', 'surger', 'icu'],
    'marriage': ['marry', 'married', 'marries', 'marriage', 'wed', 'engag', 'divorc'],
    'crash': ['crash', 'accident', 'collid', 'collision'],
}

_ANALYZER_STOP_WORDS = {
    'is', 'it', 'that', 'this', 'in', 'on', 'at', 'for', 'to', 'a', 'an', 'the', 'of', 'and', 'or', 'with', 'by', 'from',
    'new', 'now', 'was', 'were', 'will', 'be', 'has', 'have', 'had', 'do', 'does', 'did', 'about', 'he', 'she', 'they', 
    'them', 'me', 'him', 'her', 'i', 'my', 'his', 'their', 'our', 'us', 'its'
}


def normalize_subject(subject: str) -> str:
    """Normalize query subject to base form by stripping possessive and plural markers."""
    s = subject.lower().strip()
    s = re.sub(r'[\'’]s$', '', s)
    if len(s) > 4 and s.endswith('s') and not s.endswith('ss'):
        s = s[:-1]
    return s


def extract_query_subjects(query: str) -> list[str]:
    """Extract key non-stopword entity subjects from the query."""
    words = query.split()
    cap_words = [re.sub(r'[^\w]', '', w) for w in words if w and w[0].isupper()]
    if cap_words:
        return [normalize_subject(w) for w in cap_words if normalize_subject(w) not in _ANALYZER_STOP_WORDS]
    
    q_words = clean_text(query).split()
    subjects = []
    for w in q_words:
        w_norm = normalize_subject(w)
        if len(w_norm) < 3:
            continue
        if w_norm in _ANALYZER_STOP_WORDS:
            continue
        # Check if it's in any event verb group
        is_verb = False
        for group in EVENT_VERB_GROUPS.values():
            if w_norm in group:
                is_verb = True
                break
        if not is_verb:
            subjects.append(w_norm)
    return subjects


def get_query_event_groups(query: str) -> list[str]:
    """Identify which event verb groups are mentioned in the query using robust stem matching."""
    q_words = query.lower().split()
    matched_groups = []
    for group_name, stems in EVENT_VERB_STEMS.items():
        for stem in stems:
            if any(w.startswith(stem) for w in q_words):
                matched_groups.append(group_name)
                break
    return matched_groups


def find_subject_in_title(subject: str, title_lower: str) -> str | None:
    """Fuzzy match a query subject inside the article title to handle typos in query names."""
    import difflib
    words = re.findall(r'\b[a-z]{3,}\b', title_lower)
    for w in words:
        if w == subject:
            return w
        if len(subject) >= 4 and len(w) >= 4:
            if difflib.SequenceMatcher(None, subject, w).ratio() >= 0.80:
                return w
    return None


def verify_claim_support(query: str, title: str, summary: str, url: str) -> float:
    """
    Analyze if the retrieved article actually supports the query's specific claim.
    Returns a multiplier (0.0 to 1.0) to scale down similarity if a mismatch is found.
    Handles user typos and grammatical tenses.
    """
    title_lower = title.lower()
    summary_lower = summary.lower()
    text_lower = title_lower + " " + summary_lower
    url_lower = url.lower()
    
    multiplier = 1.0
    
    # 1. Question penalty
    if "?" in title or title_lower.startswith(("why ", "how ", "will ", "would ", "is ", "can ", "could ", "should ")):
        multiplier *= 0.5
        
    # 2. Opinion penalty
    if any(w in title_lower or w in url_lower for w in ("opinion", "editorial", "column", "perspective")):
        multiplier *= 0.5
        
    # 3. Event alignment check
    q_event_groups = get_query_event_groups(query)
    q_subjects = extract_query_subjects(query)
    
    if q_event_groups:
        # Check if article mentions the same event type (using expanded clean groups)
        has_matching_event = False
        for group in q_event_groups:
            group_words = EVENT_VERB_GROUPS[group]
            if any(re.search(r'\b' + re.escape(w) + r'\b', text_lower) for w in group_words):
                has_matching_event = True
                break
        if not has_matching_event:
            # Article doesn't even mention the verb/event! Major penalty.
            return 0.15
            
        # Check specific mismatch conditions using matched title subjects
        for subject in q_subjects:
            matched_subj = find_subject_in_title(subject, title_lower)
            if not matched_subj:
                continue
                
            # A. Speaker/Attribution mismatch
            speaker_patterns = [
                # subject followed by speech verb (optionally separated by up to 6 words)
                rf'\b{re.escape(matched_subj)}\b[^.:?]*\b(says|warns|warned|said|claims|claimed|threatens|threatened|asserts|speaks|spoke|on)\b',
                # speech verb followed by subject
                rf'\b(says|said|warns|warned|claims|according to)\b[^.:?]*\b{re.escape(matched_subj)}\b',
                # subject after colon (like [Quote]: Trump)
                rf':[^:]*\b{re.escape(matched_subj)}\b',
                # subject before colon (like Trump: '...')
                rf'\b{re.escape(matched_subj)}\b[^.:?]*:[^:]*$',
            ]
            if any(re.search(pattern, title_lower) for pattern in speaker_patterns):
                multiplier *= 0.20
                
            # B. Possessive/Modifier mismatch: e.g. "Trump's Gaza plan to die"
            possessive_patterns = [
                rf'\b{re.escape(matched_subj)}[\'’]s\s+\w+',
                rf'\b{re.escape(matched_subj)}\s+(plan|campaign|administration|lawyer|lawyers|legal team|defense|ally|allies|supporters|organization|org|foundation|business|brand|hotels|golf|rally|speech|threat|warning)\b'
            ]
            if any(re.search(pattern, title_lower) for pattern in possessive_patterns):
                multiplier *= 0.30

            # C. Subject mismatch: e.g. "Robert Mueller dies" (where subject of dies is not our subject Trump)
            for group in q_event_groups:
                for verb in EVENT_VERB_GROUPS[group]:
                    # Find instances of "[Name] [verb]" in title
                    matches = re.finditer(rf'\b([a-zA-Z]+)[^\w\s]*\s+{re.escape(verb)}\b', title_lower)
                    for m in matches:
                        name = m.group(1)
                        if name != matched_subj and name not in _ANALYZER_STOP_WORDS and len(name) >= 3:
                            multiplier *= 0.25
                            
    return multiplier


