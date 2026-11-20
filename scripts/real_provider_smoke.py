import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings
from app.llm import CallBudget, HostedLLM, verify_draft
from app.schemas import Chunk

async def smoke_test():
    print("=" * 60)
    print("CommutePolicy AI — Live LLM Provider Smoke Test")
    print("=" * 60)
    
    try:
        settings = Settings()
    except Exception as exc:
        print(f"[ERROR] Failed to load settings: {exc}")
        return 1

    api_key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else ""
    if not api_key or api_key in ("mock-dev-key", "sk-placeholder", "your-api-key-here", ""):
        print("\n[INFO] Real LLM provider is NOT configured.")
        print("Reason: LLM_API_KEY is not set in .env.")
        print("\nTo run smoke tests against a live hosted LLM provider:")
        print("  1. Edit .env in CommutePolicy-AI/")
        print("  2. Set LLM_API_KEY=<your-key>")
        print("  3. Set LLM_MODEL=<model-name> (e.g. gpt-4o-mini)")
        print("  4. Set LLM_BASE_URL=<base-url> (e.g. https://api.openai.com/v1)")
        print("\nDeterministic offline evaluation and automated tests use FakeLLM + real SentenceTransformers.")
        print("[STATUS] Smoke test skipped cleanly (no credentials configured).")
        return 0

    print(f"Provider: {settings.llm_provider}")
    print(f"Model:    {settings.llm_model}")
    print(f"Base URL: {settings.llm_base_url}")
    print(f"Timeout:  {settings.llm_timeout}s")

    llm = HostedLLM(settings)
    budget = CallBudget()

    # Create synthetic test chunk
    chunk = Chunk(
        chunk_id="test_chunk_001",
        company_id="COMPANY_A",
        policy_id="policy_001",
        policy_version="v1",
        document_name="Apex_Transport_Policy_v1.txt",
        section_number="4.2",
        section_title="Security Escorts for Late Night Travel",
        page_number=3,
        text="Section 4.2 Security Escorts: For trips scheduled after 20:00 (8:00 PM), female employees travelling alone or as the last drop are assigned a dedicated security escort.",
        content_hash="hash_001_abc"
    )

    question = "Do female employees need an escort for an 8:30 PM drop?"
    print(f"\nQuestion: {question}")
    print(f"Evidence: Chunk {chunk.chunk_id} (Section {chunk.section_number})")

    start = time.perf_counter()
    try:
        raw_response = await llm.complete(question, [chunk], budget)
        latency_ms = (time.perf_counter() - start) * 1000
        print(f"\nResponse received in {latency_ms:.1f}ms:")
        print(f"Raw Output: {raw_response}")

        draft, citations = verify_draft(raw_response, [chunk], "COMPANY_A", "v1")
        print("\n[SUCCESS] Response passed strict schema and citation validation!")
        print(f"  Status:    {draft.status}")
        print(f"  Answer:    {draft.answer}")
        print(f"  Citations: {[c.chunk_id for c in citations]}")
        return 0
    except Exception as exc:
        print(f"\n[FAILURE] Smoke test encountered an error: {type(exc).__name__}: {exc}")
        return 1
    finally:
        await llm.close()

if __name__ == "__main__":
    code = asyncio.run(smoke_test())
    sys.exit(code)
