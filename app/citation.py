"""Citation verification — Python-side, not LLM-side."""
from typing import Any

def verify_citations(
    chunk_ids: list[str],
    retrieved_chunks: list[dict],
    company_id: str,
    active_version: str,
) -> list[dict[str, Any]]:
    """
    Verify each cited chunk_id:
    1. Was it actually retrieved in this request?
    2. Does it belong to the authenticated company?
    3. Does it belong to the active policy version?
    Returns list of verified citation dicts with display metadata.
    Silently drops invalid citations (never fabricate).
    """
    retrieved_map = {
        (c['chunk_id'] if isinstance(c, dict) else c.chunk_id): c
        for c in retrieved_chunks
    }
    verified = []
    for cid in chunk_ids[:3]:  # max 3 citations
        chunk = retrieved_map.get(cid)
        if chunk is None:
            continue  # not retrieved — drop
        c_company = chunk.get('company_id') if isinstance(chunk, dict) else getattr(chunk, 'company_id', None)
        if c_company != company_id:
            continue  # wrong tenant — drop
        c_version = chunk.get('policy_version') if isinstance(chunk, dict) else getattr(chunk, 'policy_version', None)
        if c_version != active_version:
            continue  # wrong version — drop
        doc_name = chunk.get('document_name', 'Unknown') if isinstance(chunk, dict) else getattr(chunk, 'document_name', 'Unknown')
        sec_num = chunk.get('section_number', 'N/A') if isinstance(chunk, dict) else getattr(chunk, 'section_number', 'N/A')
        sec_title = chunk.get('section_title', '') if isinstance(chunk, dict) else getattr(chunk, 'section_title', '')
        page_num = chunk.get('page_number') if isinstance(chunk, dict) else getattr(chunk, 'page_number', None)
        verified.append({
            'chunk_id': cid,
            'document_name': doc_name,
            'section_number': sec_num,
            'section_title': sec_title,
            'page_number': page_num,
        })
    return verified


def build_citation_text(citations: list[dict[str, Any]]) -> list[str]:
    """Format verified citations for display."""
    result = []
    for c in citations:
        parts = [c['document_name']]
        sec = c.get('section_number')
        title = c.get('section_title')
        if sec and sec != 'N/A':
            parts.append(f"Section {sec}" + (f" — {title}" if title else ""))
        elif title:
            parts.append(title)
        pg = c.get('page_number')
        if pg:
            parts.append(f"Page {pg}")
        result.append('\n'.join(parts))
    return result
