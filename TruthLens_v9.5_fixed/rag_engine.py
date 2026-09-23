"""
rag_engine.py — Real-time Retrieval-Augmented Generation for TruthLens

Architecture
────────────
• Concurrent RSS fetch from 16 trusted sources using ThreadPoolExecutor
• FAISS IndexFlatIP (cosine similarity via L2-normalised vectors)
• Precision boosting: keyword overlap + topic match + location filter
• Deep content verification for top-2 strong matches
• Consensus detection: 2+ Tier-1 sources above threshold → CONSENSUS_VERIFIED
• Live Google News fallback when cached index is weak (avg_sim < 0.60)
• Thread-safe reads/writes via a single threading.Lock
• Freshness filtering: stale articles (>48h) are de-ranked automatically

Match-type constants used by predictor.py:
  'Semantic'              default FAISS match
  'PRECISION_MATCH'       keyword overlap ≥ 2
  'ENTITY_MISMATCH'       location filter penalty applied
  'DEEP_CONTENT_VERIFIED' full article body verified
  'CONSENSUS_VERIFIED'    2+ Tier-1 sources agree
  'LIVE_WEB_MATCH'        Google News fallback
  'LIVE_PRECISION'        Google News + keyword boost
"""

import time
import re
import logging
import threading
import warnings
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from urllib.parse import quote as url_quote

import requests
import feedparser
import faiss
import numpy as np

try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    pass

import difflib
from analyzer import detect_topic, detect_location, match_location, GEOGRAPHY_KEYWORDS, TOPIC_KEYWORDS, verify_claim_support

STOP_WORDS = {
    'is', 'it', 'that', 'this', 'in', 'on', 'at', 'for', 'to', 'a', 'an', 'the', 'of', 'and', 'or', 'with', 'by', 'from',
    'new', 'now', 'was', 'were', 'will', 'be', 'has', 'have', 'had', 'do', 'does', 'did', 'about', 'after', 'all', 'any',
    'are', 'as', 'but', 'by', 'how', 'if', 'into', 'its', 'no', 'not', 'other', 'our', 'out', 'over', 'some', 'such', 'than',
    'then', 'there', 'these', 'they', 'this', 'those', 'through', 'too', 'under', 'until', 'up', 'very', 'what', 'when',
    'where', 'which', 'while', 'who', 'whom', 'why', 'you', 'your', 'we', 'he', 'she', 'they', 'them', 'me', 'him', 'her',
    'i', 'my', 'his', 'their', 'our', 'us', 'its', 'getting', 'gets', 'got', 'take', 'takes', 'taking', 'make', 'makes', 'making',
    'go', 'goes', 'going', 'come', 'comes', 'coming', 'want', 'wants', 'wanted', 'show', 'shows', 'showing'
}

_GEO_TOPIC_WORDS = set()
for list_words in GEOGRAPHY_KEYWORDS.values():
    for w in list_words:
        _GEO_TOPIC_WORDS.update(w.lower().split())
for list_words in TOPIC_KEYWORDS.values():
    for w in list_words:
        _GEO_TOPIC_WORDS.update(w.lower().split())

log = logging.getLogger(__name__)

# ── Source tiers ──────────────────────────────────────────────
SOURCE_TIERS: dict[str, int] = {
    # Tier 1 — gold standard
    'BBC World':            1, 'Reuters':        1,
    'Al Jazeera':           1, 'Associated Press':1,
    'The Guardian':         1, 'The Hindu':       1,
    'Times of India':       1, 'NDTV News':       1,
    'Indian Express':       1,
    'Hindustan Times':      1,
    'Deccan Herald':        1,
    'India Today':          1,
    'Moneycontrol':         1,
    'Economic Times':       1,
    'Livemint':             1,
    'IMD National':         1,
    # Tier 2 — regional / specialist
    'News18 India':         2, 'News18 Telangana':2,
    'ETV Bharat Telangana': 2, 'Telangana Today': 2,
    'Hans India':           2, 'Siasat Daily':    2,
    'Weather.com':          2, 'AccuWeather':     2,
    'ESPN Sports':          2,
    'TechCrunch':           2,
    'VentureBeat':          2,
    'Wired':                2,
    'Skymet Weather':       2,
    # Tier 2 — newly added Telugu / Indian channels
    'V6 News Telugu':       2,
    'TV9 Telugu':           2,
    'TV9 India':            2,
    'Sakshi TV':            2,
    'ABN Telugu':           2,
    'ETV Bharat Andhra Pradesh': 2,
    'Namasthe Telangana':   2,
    'The News Minute':      2,
    'Andhra Jyothy':        2,
}

# ── RSS feed list ─────────────────────────────────────────────
RSS_FEEDS: list[tuple[str, str]] = [
    # ── National English ──────────────────────────────────────
    ('The Hindu',            'https://www.thehindu.com/news/feeder/default.rss'),
    ('Times of India',       'https://timesofindia.indiatimes.com/rssfeedstopstories.cms'),
    ('NDTV News',            'https://www.ndtv.com/rss/all'),
    ('Indian Express',       'https://indianexpress.com/feed/'),
    ('News18 India',         'https://www.news18.com/rss/india.xml'),
    ('Hindustan Times',      'https://www.hindustantimes.com/rss/topnews/rssfeed.xml'),
    ('Deccan Herald',        'https://www.deccanherald.com/feed'),
    ('India Today',          'https://www.indiatoday.in/rss/home'),
    # ── Startups, Tech & Edtech ────────────────────────────────
    ('TechCrunch',           'https://techcrunch.com/feed/'),
    ('VentureBeat',          'https://venturebeat.com/feed/'),
    ('Wired',                'https://www.wired.com/feed/rss'),
    # ── Stocks & Business ─────────────────────────────────────
    ('Moneycontrol',         'https://www.moneycontrol.com/rss/MCtopnews.xml'),
    ('Economic Times',       'https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms'),
    ('Livemint',             'https://www.livemint.com/rss/markets'),
    # ── Telangana / Andhra / South India ──────────────────────
    ('News18 Telangana',     'https://telugu.news18.com/rss/telangana.xml'),
    ('ETV Bharat Telangana', 'https://www.etvbharat.com/english/rss/state/telangana'),
    ('ETV Bharat Andhra Pradesh', 'https://www.etvbharat.com/english/rss/state/andhra-pradesh'),
    ('Telangana Today',      'https://telanganatoday.com/feed'),
    ('Namasthe Telangana',   'https://ntnews.com/news/feed'),
    ('The News Minute',      'https://www.thenewsminute.com/feed'),
    ('Andhra Jyothy',        'https://www.andhrajyothy.com/rss/feed.xml'),
    # ── Telugu / Indian TV channels ───────────────────────────
    ('V6 News Telugu',       'https://www.v6news.tv/feed/'),
    ('TV9 Telugu',           'https://tv9telugu.com/feed/'),
    ('TV9 India',            'https://www.tv9hindi.com/feed'),
    ('Sakshi TV',            'https://www.sakshi.com/rss.xml'),
    ('ABN Telugu',           'https://www.andhrabhoomi.net/rss.xml'),
    # ── Global ────────────────────────────────────────────────
    ('BBC World',            'http://feeds.bbci.co.uk/news/rss.xml'),
    ('Reuters',              'https://feeds.reuters.com/reuters/topNews'),
    # ── Weather specific ─────────────────────────────────────
    ('India Met Dept',       'https://city.imd.gov.in/citywx/rss/hyd.xml'),
    ('IMD National',         'https://city.imd.gov.in/citywx/rss/national.xml'),
    ('Skymet Weather',       'https://www.skymetweather.com/feed/'),
]

_HEADERS = {'User-Agent': 'TruthLens/9.5 (+https://github.com/truthlens)'}

# ── Freshness constants ───────────────────────────────────────
FRESH_HOURS   = 48        # articles older than this get a staleness penalty
STALE_DAMPEN  = 0.55      # multiplier for stale articles (>48h old)
TODAY_HOURS   = 6         # articles within 6h are considered "today"
RECENT_HOURS  = 24        # articles within 24h are "recent"

def check_keyword_overlap(q_words: set[str], t_words: set[str]) -> int:
    import difflib
    overlap = 0
    for qw in q_words:
        if len(qw) < 3:
            continue
        for tw in t_words:
            if len(tw) < 3:
                continue
            if qw == tw:
                overlap += 1
                break
            elif len(qw) >= 4 and len(tw) >= 4:
                # Allow minor typos using difflib SequenceMatcher
                if difflib.SequenceMatcher(None, qw, tw).ratio() >= 0.78:
                    overlap += 1
                    break
    return overlap


# ── Dataclasses ───────────────────────────────────────────────

@dataclass
class Article:
    source:    str
    title:     str
    summary:   str
    url:       str
    topic:     str  = 'general'
    timestamp: float = 0.0

    @property
    def tier(self) -> int:
        return SOURCE_TIERS.get(self.source, 3)

    @property
    def age_hours(self) -> float:
        """How many hours old this article is."""
        if not self.timestamp:
            return 999.0
        return (time.time() - self.timestamp) / 3600.0

    @property
    def freshness_label(self) -> str:
        """Human-readable freshness for UI display."""
        h = self.age_hours
        if h < 1:
            return 'Just now'
        if h < 6:
            return f'{int(h)}h ago'
        if h < 24:
            return f'{int(h)}h ago'
        if h < 48:
            return 'Yesterday'
        d = int(h / 24)
        return f'{d}d ago'

    def get_favicon(self) -> str:
        from urllib.parse import urlparse
        domain = urlparse(self.url).netloc
        return f'https://www.google.com/s2/favicons?domain={domain}&sz=64'


@dataclass
class RAGResult:
    article:    Article
    similarity: float
    match_type: str = 'Semantic'


# ── RAGEngine ─────────────────────────────────────────────────

class RAGEngine:
    # Similarity thresholds
    CONSENSUS_SIM   = 0.72  # min sim for a Tier-1 article to count toward consensus
    LIVE_FALLBACK   = 0.60  # trigger live search when max_sim is below this
    KEYWORD_BOOST   = 1.35  # multiplier for keyword-overlap matches
    TOPIC_BOOST     = 1.25  # multiplier for same-topic articles
    LOCATION_DAMPEN = 0.15  # multiplier for location mismatches
    DEEP_BOOST      = 1.20  # multiplier for deep-content matches

    def __init__(self, encoder, cross_encoder=None):
        self._encoder  = encoder
        self._cross_encoder = cross_encoder
        self._articles: list[Article] = []
        self._index: faiss.IndexFlatIP | None = None
        self._last_refresh: float = 0.0
        self._lock = threading.Lock()

    # ── Properties ────────────────────────────────────────────
    @property
    def index_size(self) -> int:
        return len(self._articles)

    @property
    def last_refresh(self) -> float:
        return self._last_refresh

    # ── Internal ──────────────────────────────────────────────
    def _rebuild_index(self, articles: list[Article]) -> None:
        """Encode articles and rebuild the FAISS index. NOT thread-safe — call from refresh() only."""
        if not articles:
            return
        texts = [f"{a.topic}: {a.title} {a.summary}" for a in articles]
        embs  = self._encoder.encode(
            texts,
            batch_size=64,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).astype(np.float32)
        new_idx = faiss.IndexFlatIP(embs.shape[1])
        new_idx.add(embs)
        with self._lock:
            self._articles = articles
            self._index    = new_idx

    def _fetch_one_feed(self, source_name: str, feed_url: str) -> list[Article]:
        """Fetch and parse a single RSS feed. Returns list of Article objects."""
        found: list[Article] = []
        try:
            resp = requests.get(feed_url, timeout=10, headers=_HEADERS, verify=False)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
            for entry in feed.entries[:20]:   # increased from 15 to 20 for more coverage
                title     = (entry.get('title',   '') or '').strip()
                summary   = (entry.get('summary', '') or entry.get('description', '') or '').strip()
                entry_url = (entry.get('link',    '') or '').strip()

                # Parse timestamp — prefer published > updated > now
                ts = None
                for tfield in ('published_parsed', 'updated_parsed'):
                    if entry.get(tfield):
                        try:
                            ts = time.mktime(entry[tfield])
                            break
                        except Exception:
                            pass
                if ts is None:
                    ts = time.time()

                # Reject articles with obviously wrong timestamps (future or very old >7 days)
                now = time.time()
                if ts > now + 3600:       # future timestamp (with 1h tolerance)
                    ts = now
                if ts < now - 7 * 86400: # older than 7 days — skip entirely
                    continue

                if len(title) > 10:
                    topic = detect_topic(title + ' ' + summary)
                    found.append(Article(
                        source=source_name, title=title, summary=summary,
                        url=entry_url, topic=topic, timestamp=ts,
                    ))
        except Exception as exc:
            log.debug('Feed fetch failed [%s]: %s', source_name, exc)
        return found

    def _mock_seed(self) -> None:
        """Minimal fallback so _index is never None after the first refresh attempt."""
        mock = [
            Article(
                source='Official', url='https://telanganatoday.com/ghmc-3',
                title='GHMC trifurcation update',
                summary='Proposal for GHMC split remains under review.',
                topic='telangana', timestamp=time.time() - 3600,
            ),
        ]
        self._rebuild_index(mock)
        log.warning('RAGEngine: live RSS failed — using mock seed.')

    def scrape_article(self, url: str) -> str:
        """Fetch article body text (best-effort, ≤1500 chars)."""
        try:
            resp = requests.get(url, timeout=5, headers={'User-Agent': 'Mozilla/5.0'}, verify=False)
            html = resp.text
            html = re.sub(r'<(script|style|header|footer|nav)[^>]*>.*?</\1>', '', html, flags=re.S | re.I)
            text = re.sub(r'<[^>]+>', ' ', html)
            text = re.sub(r'\s+',     ' ', text).strip()
            return text[:1500]
        except Exception:
            return ''

    # ── Public API ─────────────────────────────────────────────
    def refresh(self) -> int:
        """
        Parallel fetch of all RSS feeds.
        Returns number of articles indexed.
        Falls back to mock seed if every feed fails.
        """
        log.info('RAG: refreshing %d feeds concurrently…', len(RSS_FEEDS))
        new_articles: list[Article] = []

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                executor.submit(self._fetch_one_feed, src, url): src
                for src, url in RSS_FEEDS
            }
            for future in concurrent.futures.as_completed(futures):
                try:
                    new_articles.extend(future.result())
                except Exception as exc:
                    log.debug('Feed future error: %s', exc)

        if new_articles:
            # Deduplicate by URL
            seen_urls = set()
            deduped = []
            for a in new_articles:
                if a.url not in seen_urls:
                    seen_urls.add(a.url)
                    deduped.append(a)
            # Sort by freshness (newest first) so index reflects recency
            deduped.sort(key=lambda a: a.timestamp, reverse=True)
            self._rebuild_index(deduped)
            self._last_refresh = time.time()
            log.info('RAG index built: %d articles (deduplicated from %d).', len(deduped), len(new_articles))
            return len(deduped)

        # All feeds failed
        with self._lock:
            if self._index is None:
                self._mock_seed()
        return 0

    def _staleness_factor(self, article: Article, temporality: str) -> float:
        """
        Return a multiplier (0-1) based on article age and query temporality.
        
        - 'today' queries: heavy penalty for articles > 24h old
        - 'yesterday' queries: prefer articles from 20-48h ago
        - 'recent' queries: penalty for articles > 72h old
        - 'any': gentle penalty for articles > 48h old
        """
        age_h = article.age_hours
        if temporality == 'today':
            if age_h <= TODAY_HOURS:  return 1.00
            if age_h <= 24:           return 0.80
            if age_h <= 48:           return 0.40
            return 0.15  # strongly penalise old articles for "today" queries
        elif temporality == 'tomorrow':
            # For "tomorrow" predictions: live/forecast feeds are best
            if age_h <= 12:  return 1.00
            if age_h <= 48:  return 0.70
            return 0.30
        elif temporality == 'yesterday':
            if 20 <= age_h <= 50:  return 1.00
            if age_h <= 72:        return 0.70
            return 0.35
        elif temporality == 'week':
            if age_h <= 7 * 24:  return 1.00
            return 0.45
        elif temporality == 'month':
            if age_h <= 30 * 24:  return 1.00
            return 0.30
        elif temporality == 'recent':
            if age_h <= RECENT_HOURS:    return 1.00
            if age_h <= FRESH_HOURS:     return 0.80
            return STALE_DAMPEN
        else:  # 'any'
            if age_h <= FRESH_HOURS:     return 1.00
            if age_h <= 7 * 24:          return STALE_DAMPEN
            return 0.25

    def search(self, query: str, top_k: int = 8, temporality: str = 'any') -> tuple[list[RAGResult], float]:
        """
        Semantic search with precision boosting, location filtering, topic bonus,
        freshness filtering, deep-content verification, and consensus detection.

        Returns (results, avg_similarity).
        """
        with self._lock:
            if self._index is None:
                return [], 0.5       # neutral when index not built yet

        query_topic = detect_topic(query)
        query_loc   = detect_location(query)

        # Embed query with topic prefix (same strategy as index)
        qv = self._encoder.encode(
            [f'{query_topic}: {query}'],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).astype(np.float32)

        with self._lock:
            n_articles = len(self._articles)
            D, I = self._index.search(qv, k=min(top_k * 4, n_articles))
            articles_snap = list(self._articles)   # snapshot inside lock

        q_words = set(query.lower().split())
        results: list[RAGResult] = []

        candidates = []
        candidate_indices = []
        for i, idx in enumerate(I[0]):
            if idx < 0 or idx >= len(articles_snap):
                continue
            candidates.append(articles_snap[idx])
            candidate_indices.append(i)

        ce_scores = []
        if self._cross_encoder and candidates:
            pairs = [[query, f"{art.title} {art.summary}"] for art in candidates]
            raw_scores = self._cross_encoder.predict(pairs, show_progress_bar=False)
            ce_scores = [1.0 / (1.0 + np.exp(-float(s))) for s in raw_scores]

        for idx_in_cand, art in enumerate(candidates):
            orig_idx = candidate_indices[idx_in_cand]
            if ce_scores:
                sim = ce_scores[idx_in_cand]
                m_type = 'CrossEncoder'
            else:
                sim = float(D[0][orig_idx])
                m_type = 'Semantic'

            # Keyword precision boost
            t_words = set(art.title.lower().split())
            if check_keyword_overlap(q_words, t_words) >= 2:
                sim    = min(0.99, sim * self.KEYWORD_BOOST)
                m_type = 'CE_PRECISION' if ce_scores else 'PRECISION_MATCH'

            # Location penalty — hard mismatch → nearly discard
            art_text = (art.title + ' ' + art.summary).lower()

            # Check if source is regional for query_loc
            is_regional_match = False
            source_lower = art.source.lower()
            if query_loc == 'telangana':
                regional_keywords = {
                    'telangana', 'hyderabad', 'deccan chronicle', 'v6 news', 
                    'tv9 telugu', 'sakshi', 'abn', 'andhra jyothy', 'news minute', 
                    'hans india', 'siasat', 'etv bharat', 'metro', 'skymet'
                }
                if any(kw in source_lower for kw in regional_keywords):
                    is_regional_match = True
            elif query_loc == 'andhra':
                regional_keywords = {
                    'andhra', 'vijayawada', 'visakhapatnam', 'amaravati', 
                    'tv9 telugu', 'sakshi', 'abn', 'andhra jyothy', 'news minute', 
                    'hans india', 'deccan chronicle', 'etv bharat'
                }
                if any(kw in source_lower for kw in regional_keywords):
                    is_regional_match = True

            if query_loc != 'global' and not is_regional_match and not match_location(art_text, query_loc):
                sim   *= self.LOCATION_DAMPEN
                m_type = 'ENTITY_MISMATCH'

            # Topic bonus (only when location is not already mismatched)
            if (m_type != 'ENTITY_MISMATCH'
                    and art.topic == query_topic
                    and query_topic != 'general'):
                sim = min(0.99, sim * self.TOPIC_BOOST)

            # Content-word mismatch penalty (only when location is not already mismatched)
            if m_type != 'ENTITY_MISMATCH':
                core_q_words = set()
                for qw in q_words:
                    if len(qw) < 3:
                        continue
                    if qw in STOP_WORDS:
                        continue
                    if qw in _GEO_TOPIC_WORDS:
                        continue
                    core_q_words.add(qw)

                if core_q_words:
                    matched_content_count = 0
                    art_words = set(art_text.split())
                    for cqw in core_q_words:
                        matched_this = False
                        for aw in art_words:
                            aw_clean = re.sub(r'[^\w]', '', aw)
                            if len(aw_clean) < 3:
                                continue
                            if cqw == aw_clean:
                                matched_this = True
                                break
                            elif len(cqw) >= 4 and len(aw_clean) >= 4:
                                if difflib.SequenceMatcher(None, cqw, aw_clean).ratio() >= 0.78:
                                    matched_this = True
                                    break
                        if matched_this:
                            matched_content_count += 1

                    if matched_content_count == 0:
                        sim *= 0.25
                        m_type = 'CONTENT_MISMATCH'

            # ── Freshness / staleness factor ─────────────────────
            stale_factor = self._staleness_factor(art, temporality)
            sim *= stale_factor

            # Apply claim support verification
            val_mult = verify_claim_support(query, art.title, art.summary, art.url)
            sim *= val_mult
            if val_mult < 1.0:
                m_type = 'CLAIM_MISMATCH'

            results.append(RAGResult(article=art, similarity=sim, match_type=m_type))

        # Sort by similarity descending
        results.sort(key=lambda r: r.similarity, reverse=True)

        # Deep content verification for top-2 strong matches
        for res in results[:2]:
            if res.similarity > 0.45:
                body = self.scrape_article(res.article.url)
                if body:
                    qv2 = self._encoder.encode(
                        [query], convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False
                    ).astype(np.float32)
                    bv  = self._encoder.encode(
                        [body[:1500]], convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False
                    ).astype(np.float32)
                    deep_sim = float(np.dot(bv, qv2.T).flatten()[0])
                    if deep_sim > res.similarity:
                        res.similarity = min(0.99, deep_sim * self.DEEP_BOOST)
                        res.match_type = 'DEEP_CONTENT_VERIFIED'

        # Consensus detection — 2+ Tier-1 sources above CONSENSUS_SIM
        tier1_hits = [
            r for r in results[:5]
            if r.article.tier == 1 and r.similarity > self.CONSENSUS_SIM
        ]
        if len(tier1_hits) >= 2:
            for r in results[:3]:
                r.match_type = 'CONSENSUS_VERIFIED'

        top     = results[:top_k]
        # Noise filtering: prevent low-similarity articles from dragging down high-confidence matches.
        # Average only matches with similarity >= 0.35, or fallback to the top-3 if none are >= 0.35.
        strong_matches = [r.similarity for r in top if r.similarity >= 0.35]
        if strong_matches:
            avg_sim = float(np.mean(strong_matches))
        else:
            avg_sim = float(np.mean([r.similarity for r in top[:3]])) if top else 0.5
        return top, avg_sim

    def search_live(self, query: str, top_k: int = 8) -> list[RAGResult]:
        """
        Live Google News RSS fallback for real-time claims.
        Used automatically by predictor when cached avg_sim < LIVE_FALLBACK.
        """
        safe_q    = url_quote(query)
        gnews_url = (
            f'https://news.google.com/rss/search'
            f'?q={safe_q}&hl=en-IN&gl=IN&ceid=IN:en'
        )
        live: list[RAGResult] = []
        try:
            resp = requests.get(gnews_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'}, verify=False)
            feed = feedparser.parse(resp.content)
            q_words = set(query.lower().split())

            for entry in feed.entries[:top_k]:
                title     = (entry.get('title',   '') or '').strip()
                entry_url = (entry.get('link',    '') or '').strip()
                source    = (entry.get('source', {}) or {}).get('title', 'Google News')
                summary   = (entry.get('summary', '') or '').strip()

                ts = None
                for tfield in ('published_parsed', 'updated_parsed'):
                    if entry.get(tfield):
                        try:
                            ts = time.mktime(entry[tfield])
                            break
                        except Exception:
                            pass
                if ts is None:
                    ts = time.time()

                if len(title) < 10:
                    continue

                topic = detect_topic(title)
                art   = Article(source=source, title=title, summary=summary,
                                url=entry_url, topic=topic, timestamp=ts)

                if self._cross_encoder:
                    sim = 0.0
                    m_type = 'LIVE_CE_MATCH'
                else:
                    # Compute similarity vs query
                    qv = self._encoder.encode(
                        [query], convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False
                    ).astype(np.float32)
                    av = self._encoder.encode(
                        [title], convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False
                    ).astype(np.float32)
                    sim    = float(np.dot(av, qv.T).flatten()[0])
                    m_type = 'LIVE_WEB_MATCH'

                    t_words = set(title.lower().split())
                    if check_keyword_overlap(q_words, t_words) >= 2:
                        sim    = min(0.99, sim * 1.30)
                        m_type = 'LIVE_PRECISION'

                live.append(RAGResult(article=art, similarity=sim, match_type=m_type))

            # Batch scoring for live search using Cross-Encoder if available
            if self._cross_encoder and live:
                pairs = [[query, f"{r.article.title} {r.article.summary}"] for r in live]
                raw_scores = self._cross_encoder.predict(pairs, show_progress_bar=False)
                for r, s in zip(live, raw_scores):
                    sim = 1.0 / (1.0 + np.exp(-float(s)))
                    m_type = 'LIVE_CE_MATCH'

                    t_words = set(r.article.title.lower().split())
                    if check_keyword_overlap(q_words, t_words) >= 2:
                        sim = min(0.99, sim * 1.30)
                        m_type = 'LIVE_CE_PRECISION'
                    r.similarity = sim
                    r.match_type = m_type

            # Apply claim support verification to all live results
            for r in live:
                val_mult = verify_claim_support(query, r.article.title, r.article.summary, r.article.url)
                r.similarity *= val_mult
                if val_mult < 1.0:
                    r.match_type = 'CLAIM_MISMATCH'

        except Exception as exc:
            log.debug('Live search failed: %s', exc)

        return sorted(live, key=lambda r: r.similarity, reverse=True)
