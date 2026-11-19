import json
import pytest
from app.llm import CallBudget, ProviderError, verify_draft
from scripts.fixtures import FakeLLM
from tests.conftest import headers

def payload(chunk):
    quote=chunk.text.split('\n',1)[-1].split('\n\nOperational procedure:')[0]
    return {'status':'answered','answer':quote,'citation_chunk_ids':[chunk.chunk_id],
        'support':[{'chunk_id':chunk.chunk_id,'quote':quote}],'clarifying_question':None}

def sample(app,company='COMPANY_A'):
    v=app.state.db.active(company)
    c=next(c for c in app.state.db.chunks(company,v) if c.section_number=='8')
    return v,c

def test_call_budget():
    budget=CallBudget()
    budget.consume()
    budget.consume()
    with pytest.raises(RuntimeError):
        budget.consume()
    assert budget.used==2

def test_valid_citations_and_no_invented_page(system):
    app,_=system
    v,c=sample(app)
    _,citations=verify_draft(json.dumps(payload(c)),[c],'COMPANY_A',v)
    assert citations[0].document==c.document_name and citations[0].page==c.page_number
    c=c.model_copy(update={'page_number':None})
    _,citations=verify_draft(json.dumps(payload(c)),[c],'COMPANY_A',v)
    assert citations[0].page is None

@pytest.mark.parametrize('attack',['unknown','foreign','old','four','empty','invented_quote','invented_prose'])
def test_citation_rejections(system,attack):
    app,_=system
    v,c=sample(app)
    data=payload(c)
    evidence=[c]
    if attack=='unknown':
        data['citation_chunk_ids']=['fake']
        data['support'][0]['chunk_id']='fake'
    elif attack=='foreign':
        _,foreign=sample(app,'COMPANY_B')
        data=payload(foreign)
        evidence=[foreign]
    elif attack=='old':
        v='different-active-version'
    elif attack=='four':
        data['citation_chunk_ids']*=4
        data['support']*=4
    elif attack=='empty':
        data['citation_chunk_ids']=[]
        data['support']=[]
    elif attack=='invented_quote':
        data['answer']='All employees receive unlimited free airport trips.'
        data['support'][0]['quote']=data['answer']
    else:
        data['answer']='An unsupported conclusion. '+data['answer']
    with pytest.raises(ValueError):
        verify_draft(json.dumps(data),evidence,'COMPANY_A',v)

class SequenceLLM(FakeLLM):
    def __init__(self,events):
        self.events=list(events)
        self.calls=0
    async def complete(self,q,evidence,budget,correction=False):
        self.calls+=1
        event=self.events.pop(0)
        if event=='valid':
            return await super().complete(q,evidence,budget,correction)
        budget.consume()
        if isinstance(event,Exception):
            raise event
        return event

@pytest.mark.parametrize('event',['not json','{}',json.dumps({'status':'unexpected'}),
    json.dumps({'status':'answered','answer':'fabricated','citation_chunk_ids':['missing'],
    'support':[{'chunk_id':'missing','quote':'fabricated rule'}],'clarifying_question':None})])
def test_one_bounded_correction(system,cfg,event):
    app,client=system
    llm=SequenceLLM([event,'valid'])
    app.state.chat.llm=llm
    r=client.post('/api/v1/chat',headers=headers(cfg),json={'question':'When is a security escort mandatory?'})
    assert r.status_code==200 and r.json()['status']=='answered'
    assert r.json()['llm_calls']==2 and llm.calls==2

@pytest.mark.parametrize('events',[[ProviderError('quota')],[TimeoutError('timeout')],['{}','{}']])
def test_llm_failure_fails_safely(system,cfg,events):
    app,client=system
    llm=SequenceLLM(events)
    app.state.chat.llm=llm
    r=client.post('/api/v1/chat',headers=headers(cfg),json={'question':'When is a security escort mandatory?'})
    assert r.status_code==503 and r.json()['status']=='temporary_error'
    assert r.json()['citations']==[] and r.json()['llm_calls']<=2
    assert llm.calls==len(events)

def test_transport_has_no_hidden_retries(cfg):
    # Static provider contract is supplemented by a mocked actual HTTP transport.
    import asyncio
    import httpx
    from app.llm import HostedLLM
    calls=[]
    async def exercise():
        provider=HostedLLM(cfg)
        await provider.client.aclose()
        def handler(request):
            calls.append(request)
            return httpx.Response(429,json={'error':'quota'})
        provider.client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        provider.settings.llm_base_url='https://example.invalid/v1'
        budget=CallBudget()
        with pytest.raises(ProviderError):
            await provider.complete('question',[],budget)
        assert budget.used==1
        await provider.close()
    asyncio.run(exercise())
    assert len(calls)==1
