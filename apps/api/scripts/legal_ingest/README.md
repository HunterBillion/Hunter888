# Legal Ingest Pipeline

Automated ingestion of 127-ФЗ (bankruptcy law) + court practice into `legal_document` table.

## Stages

| # | Script | Input | Output | ~time |
|---|--------|-------|--------|-------|
| 01 | `01_fetch_127fz.py` | legalacts.ru | `data/law/127fz_raw/*.html` | 30s |
| 02 | `02_parse_127fz.py` | HTML files | `data/law/127fz_structured.json` | 5s |
| 03 | `03_load_127fz_to_db.py` | JSON | `legal_document` rows | 10s |
| 04 | `04_fetch_sudact_sitemap.py` | sudact.ru/sitemap_part_*.xml.gz | `data/law/sudact_urls.txt` | 1min |
| 05 | `05_fetch_sudact_cases.py` | URL list | `data/law/cases/*.html` | 60-80min |
| 06 | `06_filter_bankruptcy_cases.py` | case HTML | `cases_filtered.json` | 2min |
| 07 | `07_chunk_hierarchical.py` | cases + 127-ФЗ | in-memory chunks | 30s |
| 08 | `08_embed_gemini.py` | chunks | `legal_document.embedding_v2` | 5-15min |

## Run all (background)

```bash
cd /Users/bubble3/Desktop/Проекты_Х/wr1/Hunter888-main/apps/api
nohup .venv/bin/bash scripts/legal_ingest/run_all.sh > scripts/legal_ingest/logs/ingest_$(date +%Y%m%d_%H%M).log 2>&1 &
tail -f scripts/legal_ingest/logs/ingest_*.log
```

## Run individual stage

```bash
.venv/bin/python scripts/legal_ingest/01_fetch_127fz.py
```

## Resume after interrupt

All stages are idempotent — already-downloaded files and already-inserted rows are skipped.

## Dependencies

- Postgres + pgvector + embedding_v2 shadow column (migration `20260417_002`)
- Python deps: `bs4`, `lxml`, `httpx`, `sqlalchemy`, `asyncpg`, `openai` (navy)
- `.env`: `DATABASE_URL_SYNC`, `LOCAL_EMBEDDING_URL`, `LOCAL_EMBEDDING_API_KEY`
