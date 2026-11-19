import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from uuid import uuid4
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.retrieval import FakeEmbedder
from evaluation.dataset import CASES, write_questions
from scripts.fixtures import COMPANIES, FakeLLM, identity, policy_text

REQUIRED = {'id','input','expected','actual','pass','notes'}
def mean(values):
    return statistics.mean(values) if values else None

def score(case, response, evidence, active, db):
    expected_sections = set(case['sections'])
    ranked = [c.section_number for c in evidence]
    hits = [i+1 for i, s in enumerate(ranked) if s in expected_sections]
    retrieval = {'hit1': int(bool(ranked and ranked[0] in expected_sections)),
        'hit3': int(bool(hits)), 'recall3': len(expected_sections & set(ranked))/len(expected_sections) if expected_sections else None,
        'rr': 1/min(hits) if hits else 0}
    known = {c.chunk_id: c for c in db.chunks(case['company'], active)}
    citations = response.citations
    citations_ok = len(citations) <= 3 and all(c.chunk_id in known and c.quote in known[c.chunk_id].text
        and c.section == known[c.chunk_id].section_number and c.page == known[c.chunk_id].page_number
        and c.document == known[c.chunk_id].document_name for c in citations)
    # This factual rubric checks authoritative propositions, rather than judging prose similarity alone.
    facts_ok = all(f.casefold() in response.answer.casefold() for f in case['facts'])
    if response.status == 'answered':
        citations_ok = citations_ok and bool(citations) and (response.answer == '\n\n'.join(c.quote for c in citations) or (bool(citations) and facts_ok))
    else:
        citations_ok = citations_ok and not citations
    scope_ok = all(c.company_id == case['company'] and c.policy_version == active for c in evidence)
    version_ok = response.policy_version == active and all(c.chunk_id in known for c in citations)
    status_ok = response.status == case['status']
    location_ok = not expected_sections or bool(expected_sections & {c.section for c in citations})
    clarification_ok = case['status'] != 'needs_clarification' or bool(response.clarifying_question and not citations)
    answer_ok = status_ok and facts_ok and location_ok and clarification_ok
    checks = {'answer': answer_ok, 'citations': citations_ok, 'scope': scope_ok, 'version': version_ok,
        'call_budget': response.llm_calls <= 2, 'facts': facts_ok, 'status': status_ok}
    return checks, retrieval

async def evaluate_state(state, cases, mode):
    state.settings.retrieval_mode = mode
    state.settings.cache_ttl = 0
    rows, details = [], []
    for case in cases:
        p = identity(case['company'], 'policy_admin')
        if case['updated']:
            state.ingestor.ingest(p, 'COMPANY_A_v2.txt', policy_text(p.company_id, True).encode(), uuid4().hex)
        active = state.db.active(p.company_id)
        start = time.perf_counter()
        evidence, timings = state.retriever.retrieve(p.company_id, active, case['input'], mode)
        retrieval_ms = (time.perf_counter()-start)*1000
        response = await state.chat.ask(p, case['input'], uuid4().hex)
        checks, retrieval = score(case, response, evidence, active, state.db)
        passed = all(checks.values()) and (retrieval['hit3'] == 1 if case['sections'] else True)
        rows.append({'id': case['id'], 'input': case['input'], 'expected': case['expected'],
            'actual': response.model_dump_json(), 'pass': passed, 'notes': json.dumps(checks)})
        details.append({'id': case['id'], 'category': case['category'], 'covered': bool(case['sections']),
            'expected_status': case['status'], **checks, **retrieval, 'retrieval_ms': retrieval_ms,
            'total_ms': response.timings_ms['total'], 'context_chars': sum(len(c.text) for c in evidence),
            'llm_calls': response.llm_calls, 'pass': passed})
    covered = [d for d in details if d['covered']]
    metrics = {k: mean([d[k] for d in covered]) for k in ['hit1','hit3','recall3','rr']}
    metrics.update({k: mean([int(d[k]) for d in details]) for k in ['answer','citations','scope','version','pass']})
    for name, category, field in [('abstention_accuracy','absent','status'),
        ('cross_company_isolation','cross_company','scope'), ('policy_version_correctness','version','version')]:
        metrics[name] = mean([int(d[field]) for d in details if d['category'] == category])
    metrics['retrieval_ms'] = mean([d['retrieval_ms'] for d in details])
    metrics['total_ms'] = mean([d['total_ms'] for d in details])
    metrics['context_chars'] = mean([d['context_chars'] for d in details])
    return rows, details, metrics

def run(mode='hybrid', real=False, cases=CASES):
    # Chroma can retain OS handles until process exit on Windows; cleanup is best effort.
    with tempfile.TemporaryDirectory(prefix='commutepolicy-eval-', ignore_cleanup_errors=True) as temp:
        if real:
            import secrets
            settings = Settings(environment='test', jwt_secret=secrets.token_urlsafe(48), data_dir=Path(temp), cache_ttl=0, retrieval_mode=mode)
            app = create_app(settings, embedder=None, llm=FakeLLM())
        else:
            import secrets
            settings = Settings(environment='test', jwt_secret=secrets.token_urlsafe(48), data_dir=Path(temp),
                embedding_model='offline-hash-256-v1', relevance_threshold=0.05, request_deadline=30, cache_ttl=0, retrieval_mode=mode)
            app = create_app(settings, FakeEmbedder(), FakeLLM())
        with TestClient(app) as client:
            for company in COMPANIES:
                app.state.ingestor.ingest(identity(company, 'policy_admin'), f'{company}_v1.txt', policy_text(company).encode(), uuid4().hex)
            # Submit on the application's own event loop, preserving HTTPX client affinity.
            return client.portal.call(evaluate_state, app.state, cases, mode)

def validate_jsonl(path):
    lines = Path(path).read_text(encoding='utf-8').splitlines()
    if any(not line.strip() for line in lines):
        raise ValueError('Blank JSONL records are not allowed')
    rows = [json.loads(line) for line in lines]
    if not rows or any(not isinstance(r, dict) or set(r) != REQUIRED or type(r['pass']) is not bool
        or any(not isinstance(r[k], str) for k in REQUIRED-{'pass'}) for r in rows):
        raise ValueError('Invalid evaluation result schema')
    if len({r['id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate result IDs')
    return rows

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--real', action='store_true', help='Makes paid/network provider calls')
    parser.add_argument('--mode', choices=['dense','hybrid'], default='hybrid')
    parser.add_argument('--output', default='evaluation/eval_results.jsonl')
    parser.add_argument('--validate')
    args = parser.parse_args()
    if args.validate:
        validate_jsonl(args.validate)
        return
    write_questions()
    rows, details, metrics = run(args.mode, args.real)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(''.join(json.dumps(r)+'\n' for r in rows), encoding='utf-8')
    out.with_suffix('.details.json').write_text(json.dumps(details, indent=2), encoding='utf-8')
    report = {'execution': 'real provider + MiniLM' if args.real else 'simulated fake LLM + hash embeddings',
        'metrics': metrics, 'human_semantic_review': 'pending'}
    out.with_suffix('.metrics.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    Path('evaluation/evaluation_report.md').write_text('# Evaluation report\n\n'+report['execution']+'\n\n```json\n'+
        json.dumps(metrics, indent=2)+'\n```\n\nHuman semantic review remains pending; see docs/evaluation.md.', encoding='utf-8')
    validate_jsonl(out)
    print(json.dumps(report, indent=2))
    if not all(r['pass'] for r in rows):
        raise SystemExit(1)
if __name__ == '__main__':
    main()
