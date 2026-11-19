import json
from uuid import uuid4
import pytest
from scripts.fixtures import identity, policy_text
from tests.conftest import headers

def test_end_to_end_chat_feedback_update(system,cfg):
    app,client=system
    r=client.post('/api/v1/chat',headers=headers(cfg),json={'question':'When is a security escort required?'})
    assert r.status_code==200
    first=r.json()
    assert first['status']=='answered' and first['citations']
    assert 'after 8 PM' in first['answer'] and first['llm_calls']==1
    feedback={'request_id':first['request_id'],'helpful':True,'reason':'Clear source'}
    assert client.post('/api/v1/feedback',headers=headers(cfg),json=feedback).status_code==201
    assert client.post('/api/v1/feedback',headers=headers(cfg,'COMPANY_B'),json=feedback).status_code==404
    upload=client.post('/api/v1/admin/policies/upload',headers=headers(cfg,role='policy_admin'),
        files={'file':('v2.txt',policy_text('COMPANY_A',True).encode())})
    assert upload.status_code==201
    after=client.post('/api/v1/chat',headers=headers(cfg),json={'question':'When is a security escort required?'}).json()
    assert after['policy_version']==upload.json()['id']
    assert 'after 9 PM' in after['answer'] and 'after 8 PM' not in after['answer']

def test_not_covered_and_ambiguity(system,cfg):
    _,client=system
    for question,status in [('Does the company reimburse a personal bicycle?','not_covered'),
                            ('Can I get a cab tomorrow?','needs_clarification')]:
        r=client.post('/api/v1/chat',headers=headers(cfg),json={'question':question})
        assert r.status_code==200 and r.json()['status']==status
        assert not r.json()['citations'] and 'transport desk' in r.json()['fallback']

def test_retrieval_rejects_corrupt_cross_company_vectors(system,monkeypatch):
    app,_=system
    v=app.state.db.active('COMPANY_A')
    foreign=app.state.db.chunks('COMPANY_B',app.state.db.active('COMPANY_B'))[0]
    monkeypatch.setattr(app.state.retriever.vectors,'search',lambda *a:[(foreign,1)])
    with pytest.raises(ValueError):
        app.state.retriever.retrieve('COMPANY_A',v,'escort')

@pytest.mark.parametrize('mode',['dense','hybrid'])
def test_retrieval_matches_and_limit(system,mode):
    app,_=system
    v=app.state.db.active('COMPANY_A')
    for question in ['security escort mandatory','airport trips approval','no-show penalties']:
        evidence,_=app.state.retriever.retrieve('COMPANY_A',v,question,mode)
        assert 0<len(evidence)<=3
        assert len({c.chunk_id for c in evidence})==len(evidence)
        assert all(c.company_id=='COMPANY_A' and c.policy_version==v for c in evidence)

def test_empty_retrieval_is_safe(system):
    app,_=system
    evidence,_=app.state.retriever.retrieve('COMPANY_A','unknown-version','question')
    assert evidence==[]

def test_cache_is_tenant_version_scoped(system,cfg):
    app,client=system
    cfg.cache_ttl=60
    def ask(company):
        return client.post('/api/v1/chat',headers=headers(cfg,company),json={'question':'When is a security escort mandatory?'}).json()
    a=ask('COMPANY_A')
    assert a['status']=='answered' and not a['cached']
    repeat=ask('COMPANY_A')
    assert repeat['cached'] and repeat['llm_calls']==0 and repeat['request_id']!=a['request_id']
    b=ask('COMPANY_B')
    assert not b['cached'] and 'after 10 PM' in b['answer']
    app.state.ingestor.ingest(identity('COMPANY_A','policy_admin'),'v2.txt',policy_text('COMPANY_A',True).encode(),uuid4().hex)
    updated=ask('COMPANY_A')
    assert not updated['cached'] and 'after 9 PM' in updated['answer']

def test_rate_limit(system,cfg):
    app,client=system
    app.state.limiter.limit=1
    client.post('/api/v1/chat',headers=headers(cfg),json={'question':'Escort rule?'})
    r=client.post('/api/v1/chat',headers=headers(cfg),json={'question':'Escort rule?'})
    assert r.status_code==429 and r.headers['Retry-After']=='60'

def test_dataset_structure_and_result_jsonl(tmp_path):
    from evaluation.dataset import CASES,write_questions
    from scripts.run_evaluation import validate_jsonl
    assert len(CASES)>=20 and len({c['id'] for c in CASES})==len(CASES)
    path=tmp_path/'questions.jsonl'
    write_questions(path)
    assert len(path.read_text().splitlines())==len(CASES)
    result=tmp_path/'results.jsonl'
    result.write_text(json.dumps({'id':'eval_001','input':'q','expected':'e','actual':'a','pass':True,'notes':'n'})+'\n')
    assert len(validate_jsonl(result))==1
    result.write_text('{}\n')
    with pytest.raises(ValueError):
        validate_jsonl(result)

@pytest.mark.evaluation
def test_fixed_fake_evaluation():
    from scripts.run_evaluation import run
    rows,details,metrics=run()
    assert len(rows)>=20
    assert all(r['pass'] for r in rows), [r for r in rows if not r['pass']]
    assert all(d['llm_calls']<=2 for d in details)
    assert metrics['scope']==1 and metrics['version']==1
