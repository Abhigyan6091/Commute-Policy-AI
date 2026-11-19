# API

All protected requests use `Authorization: Bearer <JWT>`. Tenant IDs are never request parameters. Each response has `X-Request-ID`. 401 means invalid/expired identity, 403 requires administrator role, 404 means no resource within the caller's scope, 413 file too large, 422 invalid request/document, 429 local rate limit, and 503 temporary dependency/provider failure.

- GET /health: basic readiness of SQLite/Chroma; provider reachability is not checked.
- POST /api/v1/chat: JSON `{"question":"When is a security escort mandatory?"}`. Response status answered/not_covered/needs_clarification/temporary_error. Citations contain chunk_id, document, section, section_title, page (or null), and original quote. policy_version is an opaque version ID. timings_ms includes available stages; llm_calls is this request's actual invocation count.
- POST /api/v1/admin/policies/upload: multipart field file only. Returns the new version with HTTP 201 after activation. Synchronous ingestion has STAGING/ACTIVE/FAILED lifecycle metadata; failures retain old active policy.
- GET /api/v1/admin/policies/versions: caller-company history, newest first.
- GET /api/v1/admin/policies/versions/{version_id}: status/metadata within caller-company scope.
- GET /api/v1/admin/policies/current: active version or 404.
- GET /api/v1/admin/audit?limit=50&offset=0: company-scoped events, limit 1–200.
- POST /api/v1/feedback: JSON `{"request_id":"32-hex-answer-id","helpful":true,"reason":"Clear quotation"}`. Request ID must refer to the same authenticated user's answer; returns 201.

Example PowerShell with a short-lived token:

```powershell
$headers = @{ Authorization = 'Bearer <token>' }
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/chat -Method Post -Headers $headers -ContentType application/json -Body '{"question":"When is a security escort mandatory?"}'
```

No chat history or employee profile is silently inferred. If individual eligibility needs grade, shift, distance or trip type, the assistant requests clarification; users can submit a new explicit question. Every normal response includes a transport-desk fallback.
