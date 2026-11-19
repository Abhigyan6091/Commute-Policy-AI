# Dense versus hybrid

{
  "execution": "real provider",
  "dense": {
    "hit1": 0.9473684210526315,
    "hit3": 1,
    "recall3": 1.0,
    "rr": 0.9736842105263158,
    "answer": 1,
    "citations": 1,
    "scope": 1,
    "version": 1,
    "pass": 1,
    "abstention_accuracy": 1,
    "cross_company_isolation": 1,
    "policy_version_correctness": 1,
    "retrieval_ms": 86.67641922903175,
    "total_ms": 104.83996153813608,
    "context_chars": 1992.1923076923076
  },
  "hybrid": {
    "hit1": 0.9473684210526315,
    "hit3": 1,
    "recall3": 1.0,
    "rr": 0.9736842105263158,
    "answer": 1,
    "citations": 1,
    "scope": 1,
    "version": 1,
    "pass": 1,
    "abstention_accuracy": 1,
    "cross_company_isolation": 1,
    "policy_version_correctness": 1,
    "retrieval_ms": 77.45045769395522,
    "total_ms": 107.27950384450826,
    "context_chars": 2161.5
  },
  "deltas": {
    "hit1": 0.0,
    "hit3": 0,
    "recall3": 0.0,
    "rr": 0.0,
    "retrieval_ms": -9.225961535076536,
    "total_ms": 2.439542306372175,
    "context_chars": 169.30769230769238
  },
  "regressions": [],
  "conclusion": "No measured retrieval improvement on this dataset."
}

Hybrid adds a bounded BM25 index and RRF merging per tenant/version. BM25 has O(N) lexical scoring and stores token statistics in memory; the index cache holds at most 24 versions. The dense relevance gate applies in both modes. Repeated runs and human semantic review are required. Hash-embedding results do not establish real MiniLM retrieval quality.