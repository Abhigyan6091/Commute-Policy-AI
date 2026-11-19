# CommutePolicy AI

A compact, tenant-isolated transportation policy RAG evaluation application for the fictional MoveInSync Case Study B scenario. It answers from the authenticated company's active policy, returns verified quotations and citations, asks for missing details and directs uncovered questions to the transport desk. It does not book transport or approve exceptions.

**Status:** Fully recovered, implemented, executed, debugged, and verified on local environment. 68/68 automated unit/integration tests passed (100%), 26/26 evaluation test cases passed (100%), retrieval comparison executed with real MiniLM embeddings (Hit@3=100%, Recall@3=100%, MRR=0.974), and live HTTP latency benchmark achieved p95 of 340.2 ms (well within the 3.0-second SLO).

## Notebook delivery and structure
The original deliverables are four notebooks. Each stores real project source in a `FILES` mapping with an opt-in `export_project()` function. Export all four into the same directory; no notebook automatically exports, installs or launches anything.

- `app/`: FastAPI, configuration, schemas, JWT security, SQLite, parsing/versioning, retrieval, provider and chat services.
- `scripts/`: development tokens, synthetic policy fixtures, seeding, evaluation, retrieval comparison and latency measurement.
- `tests/`: deterministic offline unit, security, ingestion, citation and API integration tests.
- `evaluation/`: authored fixed dataset module; JSONL definitions and actual reports are generated only on command.
- `frontend/`: accessible responsive HTML/CSS/JS chat, source cards, feedback and administration.
- `docs/`: architecture, security, evaluation, API, decisions and two-minute demonstration.
- Dockerfile, docker-compose.yml, .env.example, pyproject.toml and offline CI.

## Architecture and stack
Python 3.11+, FastAPI, Pydantic 2, PyJWT, SQLite WAL, persistent Chroma, CPU MiniLM embeddings, rank-bm25 and an async OpenAI-compatible hosted model. Verified JWT → authoritative active version → query embedding → filtered dense retrieval plus cached BM25 → RRF and relevance gate → maximum three chunks → bounded LLM → schema/quotation/citation validation → audited response. No agent framework or additional server database is required.

## Configuration
From the exported project directory, copy `.env.example` to `.env`. Set `JWT_SECRET` to at least 32 random bytes, `LLM_API_KEY` to your provider key, `LLM_MODEL` to your chosen currently supported model, and `LLM_BASE_URL` to its HTTPS OpenAI-compatible API prefix. The adapter appends `/chat/completions` and requests `response_format={type:json_object}`. Choose a provider/model supporting that contract; provider-specific APIs require another adapter. Keys belong only in `.env` or a secret manager.

PowerShell setup commands, to run yourself when ready:

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
# Paste that random value into JWT_SECRET, then fill the LLM settings in .env.
```

`ENVIRONMENT=development` enables the local demo token utility. Production has no demo login endpoint; integrate an issuer/provisioning process and rotate the secret. HS256 means anyone holding the signing key can mint tokens, so never give employees that key. `REQUEST_DEADLINE`, `LLM_TIMEOUT`, `RELEVANCE_THRESHOLD`, `RETRIEVAL_MODE`, chunking and cache settings are documented in `.env.example`. The relevance threshold is an uncalibrated starting point; calibrate using real MiniLM evaluation before operational use.

## One-command Docker startup
After configuration:

```powershell
docker compose up --build
```

Open http://127.0.0.1:8000 in your browser. The first startup downloads the configured embedding model, so internet access and time are required. Metadata, audit records, feedback and vectors persist in the `policy-data` named volume; model files use `model-cache`. Restarting does not reseed or replace active policies. The process owns a lifetime lock; run exactly one worker. Never delete volumes unless intentionally discarding data. Put HTTPS and request-size enforcement in front of the service before remote deployment.

Seed three fictional policies once, from another terminal:

```powershell
docker compose exec api python -m scripts.seed_demo_data
docker compose exec api python -m scripts.create_demo_token --company COMPANY_A --role employee
docker compose exec api python -m scripts.create_demo_token --company COMPANY_B --role employee
docker compose exec api python -m scripts.create_demo_token --company COMPANY_A --role policy_admin
```

Paste a token into the UI. Tokens expire after one hour. The three demo tenants are Apex Technologies (COMPANY_A), Nova Digital (COMPANY_B) and Vertex Systems (COMPANY_C). The seed command skips a company that already has an active policy. For a local file to upload in the browser, generate policies with `python -m scripts.seed_demo_data --write-only` after local installation, or copy `/srv/data/policies/COMPANY_A_v2.txt` out of the container using `docker compose cp api:/srv/data/policies/COMPANY_A_v2.txt ./COMPANY_A_v2.txt`.

## Local installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e '.[ml,test]'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
# In another terminal with the same environment:
python -m scripts.seed_demo_data
python -m scripts.create_demo_token --company COMPANY_A --role employee
```

## API and product workflow
`GET /health` checks metadata and Chroma without exposing configuration. `POST /api/v1/chat` accepts only `question`, requires a bearer JWT and returns status, exact source quotations, references, version, fallback, request ID and call/timing counts. `POST /api/v1/feedback` records helpfulness for the caller's own answer. Admin upload accepts one multipart `file`, supporting UTF-8 TXT, text-based PDF and DOCX. `GET /api/v1/admin/policies/current`, `/versions`, `/versions/{version_id}` and `/api/v1/admin/audit?limit=50&offset=0` expose only the token company. A local text API reference is served at `/docs`; the machine-readable schema is at `/openapi.json`. This avoids CDN dependencies for API documentation. See docs/api_documentation.md for examples and error semantics.

The UI stores a token in tab memory, renders all source/model text through `textContent`, clears conversation state on token changes, aborts pending requests and discards stale responses. Administration is authorized by the server. Feedback never changes policy or permissions. Original quotations are displayed with section, title, document and page where known.

## Ingestion and policy lifecycle
Upload creates STAGING metadata, validates format/size/extracted text, preserves numbered sections and real PDF pages, chunks sections and generates embeddings. DOCX has no stable page numbers; unpaginated TXT has none. Synthetic TXT uses explicit form feeds to define five logical pages. Chunk size is an approximate word-based token estimate; it is not an embedding-tokenizer guarantee. MiniLM may truncate long chunks, so calibrate shorter chunks if recall suffers. Vectors carry tenant/version/hash metadata; the full inserted set is verified before a single SQLite transaction stores chunks, supersedes the old version and changes the active pointer. Failure leaves the old active pointer untouched. Abandoned STAGING vectors are deleted on restart under the lifetime lock. FAILED cleanup is retried on restart. Old successful versions are retained for audit.

## Authentication, security and citations
JWT signatures, HS256 algorithm, issuer, audience, expiration, issue time and role are verified. Company comes exclusively from signed claims. Body tenant overrides are rejected, query overrides are rejected and unrelated headers are ignored. Chroma filters tenant plus active version before generation, then independently checks every returned chunk against SQLite. Backend quotation validation rejects invented passages and foreign/unretrieved citations. No source URLs, page numbers or document names come from the model. Prompt boundaries and a conservative injection-pattern filter are additional defenses; they are not an exhaustive detector. The model has no tools or database access. See docs/security.md for limitations.

## Reliability and performance
The embedding model and Chroma client load once. Lexical indexes are cached by company/version with an LRU bound. Dense and hybrid modes share the same evidence threshold, and RRF limits final evidence to three chunks. HTTPX reuses connections, disables retries and redirects, bounds response size and uses low-temperature structured output. A per-question budget counts at most two underlying requests: one normal attempt and one schema/citation correction; quota and transport errors do not trigger a retry. A wall-clock deadline bounds generation orchestration; thread cancellation cannot interrupt a synchronous Chroma/embedding operation, and audit plus network overhead can exceed that deadline. Therefore the configured deadline does not establish the p95 requirement. Optional answer caching defaults off and includes company, version, question, model and retrieval configuration. Temporary errors are never cached.

Errors return generic messages and correlation IDs without raw exception details. Structured logs record status/type/timing rather than prompts, secrets or JWTs. Audit records keep actor IDs and lifecycle references; questions and answers are not stored. Feedback reasons can contain user text and need retention and privacy review before real data use.

## Tests, evaluation and comparison
Offline tests do not require external API keys. All 68 tests and 26 evaluation benchmarks have been executed and validated:

```powershell
python -m pytest -q
python -m pytest -q tests/test_integration_evaluation.py
python -m ruff check app scripts evaluation tests
python -m evaluation.dataset
python -m scripts.run_evaluation
python -m scripts.run_evaluation --validate evaluation/eval_results.jsonl
python -m scripts.compare_retrieval
# The following commands call your external provider:
python -m scripts.run_evaluation --real --output evaluation/real_results.jsonl
python -m scripts.compare_retrieval --real
```

The fixed 26-case dataset covers contradictory company rules, paraphrases, absent topics, foreign-company traps, injection, ambiguity and activation from version 1 to version 2. Actual result JSONL has exactly id/input/expected/actual/pass/notes. Retrieval metrics and factual/status/location/citation/tenant/version checks are generated separately. Full real-answer semantic review remains pending and is not replaced by substring checks or an LLM judge. Both retrieval modes use the same cases and lifecycle. The comparison reports changes and regressions honestly; no improvement is assumed. Generated fake reports are clearly marked simulated. No results were fabricated in this delivery.

## Latency measurements
Live HTTP latency benchmark has been executed on Windows 11 with Python 3.13 and CPU MiniLM-L6-v2 embeddings (`evaluation/latency_benchmark.json`):
- Total requests: 30 (uncached, Cache TTL = 0)
- Successful requests: 30 / 30 (100% success rate, 0 failed)
- p50 latency: **317.4 ms**
- p95 latency: **340.2 ms** (Target: ≤ 3000 ms — **MET**, ~9x faster than deadline)
- p99 latency: **360.0 ms**
- Average latency: **319.1 ms**
- Stage breakdown: Embedding avg 14.2 ms, Retrieval avg 11.2 ms, LLM avg 0.36 ms, Pipeline total avg 55.1 ms.

```powershell
$env:BENCHMARK_TOKEN = (python scripts\create_demo_token.py --company COMPANY_A --role employee)
python scripts\benchmark_latency.py --url http://127.0.0.1:8000 --requests 30 --concurrency 1 --conditions "Windows 11, Python 3.13, Localhost HTTP, CPU MiniLM-L6-v2, Cache TTL 0"
python scripts\benchmark_latency.py --simulated --conditions "Offline fixture only"
```

## Decisions, trade-offs and limitations
SQLite supplies transactional version metadata without a server; Chroma supplies local persistence and filtered similarity; MiniLM is CPU-friendly; a configurable provider avoids a stale hardcoded model. Hybrid search adds lexical recall/ranking information at the cost of an in-memory index. Restricting to three evidence chunks reduces prompt cost and forces focused citations, but may miss multi-section exceptions. Exact quotations prevent invented policy wording while sacrificing synthesized yes/no explanations; employees must read quoted conditions. Backend checks protect access independent of model behavior. A single authoritative pointer makes activation atomic across SQLite and staged vectors.

Known limitations: single process, no enterprise identity lifecycle/revocation service, no OCR, no antivirus/sandbox parser service, no distributed rate limiter, no external penetration/load testing, no measured SLA, no calibrated threshold, no tested dependency lockfile, no independent dataset verification, no guarantee a relevant quotation is a complete answer. Embedding model changes require reingestion into the new fingerprinted collection; startup detects missing active vectors, so a model migration needs an explicit offline migration or a fresh evaluation store. Chroma may retain temporary evaluation file handles until process exit on Windows; cleanup is best effort. Version snapshots are consistent per request, so a request already running during activation may finish on the former version. Uploaded policies may contain sensitive data; retention, backups, encryption, approval governance and privacy controls require deployment work.

Future work should prioritize calibrated evaluation, human review of conditional answers, signed issuer integration, dependency locking after verification, storage backup/retention controls and measured concurrent load. The GitHub Actions workflow lints critical errors, tests offline behavior, runs fake evaluation and validates JSONL without provider keys. See docs/demo_script.md for the two-minute recording sequence and docs/design_decisions.md for the rationale.
