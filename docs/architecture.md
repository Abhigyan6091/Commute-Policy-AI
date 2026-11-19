# Architecture

Browser/API → JWT verifier → SQLite active pointer → MiniLM → tenant/version-filtered Chroma and BM25 → Reciprocal Rank Fusion (RRF) → at most 3 evidence chunks → configurable hosted LLM → Pydantic schema and server-side citation verification → server-resolved citations → audit/response. Identity, permissions and scope never come from generated text or untrusted client inputs.

SQLite versions are STAGING, ACTIVE, SUPERSEDED or FAILED. The active table is authoritative. Staging vectors are invisible to normal retrieval; only fully verified versions enter a SQLite activation transaction. Current chunks and the pointer commit together. Crash recovery deletes STAGING/FAILED vector sets under the application lifetime lock. A pending ingestion cannot be mistaken for abandoned work by another worker because a second process cannot acquire that lock.

Queries pin a version at start and use it through retrieval and citation checks. Later queries resolve the pointer again. Caches are bounded and keyed by tenant/version; old versions cannot serve newly started questions. No conversation history is sent to the model, avoiding stale tenant context. One active transportation document per company is an intentional simplification.
