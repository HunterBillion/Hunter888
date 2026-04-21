"""Legal ingest pipeline — shared config."""

from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
INGEST_DIR = Path(__file__).resolve().parent
DATA_DIR = INGEST_DIR / "data" / "law"
LAW_RAW_DIR = DATA_DIR / "127fz_raw"
LAW_STRUCTURED = DATA_DIR / "127fz_structured.json"
CASES_DIR = DATA_DIR / "cases"
SUDACT_URLS_FILE = DATA_DIR / "sudact_urls_all.txt"
SUDACT_URLS_FILTERED = DATA_DIR / "sudact_urls_to_fetch.txt"
CASES_FILTERED_JSON = DATA_DIR / "cases_filtered.json"
LOGS_DIR = INGEST_DIR / "logs"

for _p in (LAW_RAW_DIR, CASES_DIR, LOGS_DIR):
    _p.mkdir(parents=True, exist_ok=True)

# ── Sources ─────────────────────────────────────────────────────────────
LEGALACTS_127FZ_URL = "https://legalacts.ru/doc/FZ-o-nesostojatelnosti-bankrotstve/"
LEGALACTS_BASE = "https://legalacts.ru"

SUDACT_SITEMAP_PARTS = [
    "https://sudact.ru/sitemap_part_0.xml.gz",
    "https://sudact.ru/sitemap_part_1.xml.gz",
]
SUDACT_BASE = "https://sudact.ru"

# ── HTTP Client ─────────────────────────────────────────────────────────
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "Hunter888-LegalIngest/1.0 (+research use, contact: admin@hunter888.ru)"
)
HTTP_TIMEOUT = 30.0

# Polite rate limit — do not stress the source
SUDACT_RPS = 0.5  # 2 seconds between requests (30 req/min)
LEGALACTS_RPS = 1.0  # 1 second between requests

# ── Bankruptcy filter keywords (case-insensitive substring match) ───────
BANKRUPTCY_KEYWORDS = [
    "банкрот",           # банкрот, банкротство, банкротный, банкротный управляющий
    "несостоятельн",     # несостоятельность, несостоятельный
    "127-фз",            # direct law reference
    "127 - фз",
    "финансовый управляющий",
    "арбитражный управляющий",
    "должника",          # must include "должник" context
    "конкурсное производство",
    "мировое соглашение",
    "внешнее управление",
    "субсидиарн",        # субсидиарная ответственность
    "реструктуризац",    # реструктуризация долгов
    "оспаривание сделок",
    "реестр требований",
]

# A case is considered "bankruptcy" if at least this many distinct keywords match
BANKRUPTCY_MIN_KEYWORDS = 3

# ── Target scope ─────────────────────────────────────────────────────────
TARGET_CASES = 500
# Prioritize Supreme Court precedents first (high legal authority),
# then arbitrage courts (where bankruptcy cases live)
CRAWL_ORDER = ["vsrf", "arbitral", "regular", "magistrate"]
# Per category max to fetch BEFORE filtering (filter keeps ~25-40% typically)
MAX_FETCH_PER_CATEGORY = {
    "vsrf": 500,        # all of them, precedent cases are gold
    "arbitral": 1500,
    "regular": 500,
    "magistrate": 300,
}

# ── Embedding ────────────────────────────────────────────────────────────
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSIONS = 768
EMBEDDING_BATCH_SIZE = 10

# ── Chunking ─────────────────────────────────────────────────────────────
# Parent-child: retrieval granularity is smaller, context is larger
CHUNK_SIZE_TARGET = 400      # tokens (heuristic: ~1200 chars for Russian)
CHUNK_SIZE_MAX = 800
CHUNK_OVERLAP = 50
# ~3 chars per token for Russian (empirical; OpenAI tokenizer-agnostic estimate)
CHARS_PER_TOKEN_RU = 3
