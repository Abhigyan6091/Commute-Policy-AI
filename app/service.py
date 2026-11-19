import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from starlette.concurrency import run_in_threadpool
from app import audit, call_budget
from app.citation import verify_citations
from app.llm import CallBudget, ProviderError
from app.schemas import ChatResponse, Citation, Draft

log = logging.getLogger('commutepolicy')
NOT_COVERED = 'I could not find a provision covering this question in your company’s current transportation policy.'

class ChatService:
    def __init__(self, db, retriever, llm, settings):
        self.db, self.retriever, self.llm, self.settings = db, retriever, llm, settings
        self.cache = OrderedDict()
    async def ask(self, p, question, request_id):
        started, budget, timings = time.perf_counter(), CallBudget(), {}
        call_budget.reset()
        version = None
        response = None
        async def remaining(awaitable):
            timeout = max(0.001, self.settings.request_deadline - (time.perf_counter()-started))
            return await asyncio.wait_for(awaitable, timeout=timeout)
        try:
            version = await remaining(run_in_threadpool(self.db.active, p.company_id))
            if version is None:
                response = ChatResponse(request_id=request_id, status='not_covered', answer=NOT_COVERED)
            else:
                key = hashlib.sha256(json.dumps([p.company_id, version, question, self.settings.llm_provider,
                    self.settings.llm_base_url, self.settings.llm_model, self.settings.embedding_model,
                    self.settings.retrieval_mode, self.settings.relevance_threshold, self.settings.llm_max_tokens]).encode()).hexdigest()
                cached = self.cache.get(key)
                if cached and cached[0] > time.monotonic():
                    response = cached[1].model_copy(deep=True, update={'request_id': request_id, 'cached': True, 'llm_calls': 0})
                    self.cache.move_to_end(key)
                else:
                    evidence, timings = await remaining(run_in_threadpool(self.retriever.retrieve, p.company_id, version, question))
                    timings['context_chars'] = sum(len(c.text) for c in evidence)
                    if not evidence:
                        response = ChatResponse(request_id=request_id, status='not_covered', answer=NOT_COVERED, policy_version=version)
                    else:
                        llm_start = time.perf_counter()
                        draft = None
                        citations = []
                        try:
                            evidence_dicts = [c.model_dump() if hasattr(c, 'model_dump') else c for c in evidence]
                            evidence_by_id = {c.chunk_id: c for c in evidence}
                            for attempt in range(2):
                                call_budget.check_budget()
                                raw = await remaining(self.llm.complete(question, evidence, budget, correction=bool(attempt)))
                                try:
                                    data = json.loads(raw)
                                    status = data.get('status')
                                    if status not in ('answered', 'not_covered', 'needs_clarification'):
                                        raise ValueError(f"Invalid status: {status}")
                                    
                                    ans = data.get('answer') or ''
                                    raw_cids = data.get('citation_chunk_ids') or []
                                    support_list = data.get('support') or []
                                    if not raw_cids and support_list:
                                        raw_cids = [s.get('chunk_id') for s in support_list if s.get('chunk_id')]
                                    clarifying = data.get('clarifying_question')
                                    
                                    if status == 'answered':
                                        if not raw_cids:
                                            raise ValueError("Answered status requires citations")
                                        if not ans or not str(ans).strip():
                                            raise ValueError("Answered status requires an answer")
                                        verified = verify_citations(raw_cids, evidence_dicts, p.company_id, version)
                                        if not verified:
                                            raise ValueError("No citations verified from evidence")
                                        
                                        support_map = {s.get('chunk_id'): s.get('quote') for s in support_list if isinstance(s, dict)}
                                        citations = []
                                        for v in verified:
                                            cid = v['chunk_id']
                                            quote = support_map.get(cid) or (evidence_by_id[cid].text if cid in evidence_by_id else '')
                                            citations.append(Citation(
                                                chunk_id=cid,
                                                document=v.get('document_name', 'Unknown'),
                                                section=v.get('section_number', 'N/A'),
                                                section_title=v.get('section_title', ''),
                                                page=v.get('page_number'),
                                                quote=quote
                                            ))
                                        draft_obj = Draft(
                                            status='answered',
                                            answer=str(ans).strip(),
                                            citation_chunk_ids=[c.chunk_id for c in citations],
                                            clarifying_question=None
                                        )
                                    elif status == 'needs_clarification':
                                        q_text = str(clarifying).strip() if clarifying and str(clarifying).strip() else ''
                                        if not q_text:
                                            raise ValueError("Clarification status requires clarifying_question")
                                        citations = []
                                        draft_obj = Draft(
                                            status='needs_clarification',
                                            answer=str(ans).strip() if ans and str(ans).strip() else q_text,
                                            citation_chunk_ids=[],
                                            clarifying_question=q_text
                                        )
                                    else:
                                        citations = []
                                        draft_obj = Draft(
                                            status='not_covered',
                                            answer=NOT_COVERED,
                                            citation_chunk_ids=[],
                                            clarifying_question=None
                                        )
                                    draft = draft_obj
                                    break
                                except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                                    if attempt == 1:
                                        raise
                        finally:
                            timings['llm'] = (time.perf_counter()-llm_start)*1000
                        
                        response = ChatResponse(
                            request_id=request_id,
                            status=draft.status,
                            answer=draft.answer,
                            citations=citations,
                            policy_version=version,
                            clarifying_question=draft.clarifying_question
                        )
                    if self.settings.cache_ttl and response.status == 'answered':
                        self.cache[key] = (time.monotonic()+self.settings.cache_ttl, response.model_copy(deep=True))
                        while len(self.cache) > self.settings.cache_entries:
                            self.cache.popitem(last=False)
        except (TimeoutError, ProviderError, ValueError, RuntimeError):
            log.warning(json.dumps({'event': 'chat_failed', 'request_id': request_id}))
            response = ChatResponse(request_id=request_id, status='temporary_error',
                answer='The policy assistant is temporarily unavailable. Please try again.', policy_version=version)
        except Exception as exc:
            log.error(json.dumps({'event': 'chat_internal_error', 'request_id': request_id, 'type': type(exc).__name__}))
            response = ChatResponse(request_id=request_id, status='temporary_error',
                answer='The policy assistant is temporarily unavailable. Please try again.', policy_version=version)
        response.llm_calls = budget.used
        response.timings_ms = {**timings, 'total': (time.perf_counter()-started)*1000}
        # Audit is deliberately awaited; failures propagate instead of reporting unaudited success.
        await run_in_threadpool(self.db.record_answer, p, response)
        try:
            audit.log_event(
                str(self.settings.data_dir / 'metadata.sqlite3'),
                'chat',
                p.company_id,
                p.user_id,
                json.dumps({'request_id': request_id, 'status': response.status, 'llm_calls': response.llm_calls})
            )
        except Exception:
            pass
        response.timings_ms['total'] = (time.perf_counter()-started)*1000
        return response
