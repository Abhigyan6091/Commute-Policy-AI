import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from filelock import FileLock
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from app import audit, call_budget, citation
from app.config import Settings
from app.database import Database
from app.ingestion import Ingestor, UploadError
from app.llm import HostedLLM
from app.retrieval import LocalEmbedder, Retriever, VectorStore
from app.schemas import AuditEvent, ChatResponse, Feedback, Principal, Question, Version
from app.security import BodyLimitMiddleware, RateLimiter, admin, principal
from app.service import ChatService

def create_app(settings=None, embedder=None, llm=None):
    @asynccontextmanager
    async def lifespan(app):
        cfg = settings or Settings()
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(cfg.data_dir/'application.lock'))
        lock.acquire(timeout=0)
        provider = None
        try:
            db = Database(cfg.data_dir/'metadata.sqlite3')
            emb = embedder or LocalEmbedder(cfg.embedding_model, cfg.embedding_device)
            vectors = VectorStore(cfg.data_dir/'chroma', cfg.embedding_model)
            ingestor = Ingestor(db, vectors, emb, cfg)
            ingestor.recover()
            if llm is not None:
                provider = llm
            elif cfg.llm_provider == 'mock' or (cfg.environment == 'development' and not cfg.llm_api_key.get_secret_value()):
                from scripts.fixtures import FakeLLM
                provider = FakeLLM()
            else:
                provider = HostedLLM(cfg)
            retriever = Retriever(db, vectors, emb, cfg)
            for row in db.active_versions():
                vectors.verify(row['company_id'], row['id'], db.chunks(row['company_id'], row['id']))
                retriever.index(row['company_id'], row['id'])
            app.state.settings, app.state.db, app.state.ingestor = cfg, db, ingestor
            app.state.retriever = retriever
            app.state.chat = ChatService(db, retriever, provider, cfg)
            app.state.limiter = RateLimiter(cfg.requests_per_minute)
            yield
        finally:
            try:
                if provider is not None:
                    await provider.close()
            finally:
                lock.release()
    app = FastAPI(title='CommutePolicy AI', version='1.0.0', lifespan=lifespan, docs_url=None, redoc_url=None)
    app.add_middleware(BodyLimitMiddleware)
    @app.middleware('http')
    async def request_context(request, call_next):
        request.state.request_id = uuid4().hex
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            logging.getLogger('commutepolicy').error(json.dumps({'event': 'request_failed',
                'request_id': request.state.request_id, 'type': type(exc).__name__}))
            response = JSONResponse({'detail': 'Service temporarily unavailable', 'request_id': request.state.request_id}, status_code=503)
        response.headers['X-Request-ID'] = request.state.request_id
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        logging.getLogger('commutepolicy').info(json.dumps({'event': 'request', 'request_id': request.state.request_id,
            'status': response.status_code, 'latency_ms': (time.perf_counter()-started)*1000}))
        return response
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        return JSONResponse({'detail': exc.detail, 'request_id': request.state.request_id},
                            status_code=exc.status_code, headers=exc.headers)
    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse({'detail': 'Invalid request fields', 'request_id': request.state.request_id}, status_code=422)
    def limited(request: Request, p: Principal = Depends(principal)):
        request.app.state.limiter.check(p.company_id, p.user_id)
        return p
    def no_tenant_query(request):
        if request.query_params:
            raise HTTPException(422, 'Query parameters are not supported for this endpoint')
    @app.get('/health', response_model=dict[str, str])
    def health(request: Request):
        with request.app.state.db.connect() as db:
            db.execute('SELECT 1').fetchone()
        request.app.state.ingestor.vectors.collection.count()
        return {'status': 'ok'}
    @app.post('/api/v1/chat', response_model=ChatResponse)
    async def chat(body: Question, request: Request, p: Principal = Depends(limited)):
        no_tenant_query(request)
        result = await request.app.state.chat.ask(p, body.question, request.state.request_id)
        return JSONResponse(result.model_dump(mode='json'), status_code=503 if result.status == 'temporary_error' else 200)
    @app.post('/api/v1/admin/policies/upload', response_model=Version, status_code=201)
    async def upload(request: Request, file: UploadFile = File(...), p: Principal = Depends(admin)):
        no_tenant_query(request)
        request.app.state.limiter.check(p.company_id, p.user_id)
        form = await request.form()
        if list(form.keys()) != ['file'] or len(form.getlist('file')) != 1:
            raise HTTPException(422, 'Upload accepts only a single file field')
        try:
            data = await file.read(request.app.state.settings.max_upload_bytes+1)
            if len(data) > request.app.state.settings.max_upload_bytes:
                raise HTTPException(413, 'File exceeds upload limit')
            return await run_in_threadpool(request.app.state.ingestor.ingest, p, file.filename or '', data, request.state.request_id)
        except UploadError as exc:
            raise HTTPException(422, str(exc)) from None
        finally:
            await file.close()
    @app.get('/api/v1/admin/policies/versions', response_model=list[Version])
    def versions(request: Request, p: Principal = Depends(admin)):
        no_tenant_query(request)
        return request.app.state.db.versions(p.company_id)
    @app.get('/api/v1/admin/policies/current', response_model=Version)
    def current(request: Request, p: Principal = Depends(admin)):
        no_tenant_query(request)
        rows = request.app.state.db.versions(p.company_id)
        row = next((r for r in rows if r['status'] == 'ACTIVE'), None)
        if row is None:
            raise HTTPException(404, 'No active policy')
        return row
    @app.get('/api/v1/admin/policies/versions/{version_id}', response_model=Version)
    def version_status(version_id: str, request: Request, p: Principal = Depends(admin)):
        no_tenant_query(request)
        row = next((r for r in request.app.state.db.versions(p.company_id) if r['id'] == version_id), None)
        if row is None:
            raise HTTPException(404, 'Version not found')
        return row
    @app.get('/api/v1/admin/audit', response_model=list[AuditEvent])
    def audit(request: Request, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), p: Principal = Depends(admin)):
        if set(request.query_params) - {'limit', 'offset'}:
            raise HTTPException(422, 'Unsupported query parameters')
        return request.app.state.db.events(p.company_id, limit, offset)
    @app.post('/api/v1/feedback', response_model=dict[str, str], status_code=201)
    def feedback(body: Feedback, request: Request, p: Principal = Depends(limited)):
        no_tenant_query(request)
        if not request.app.state.db.feedback(p, body):
            raise HTTPException(404, 'Answer not found')
        return {'status': 'recorded', 'request_id': request.state.request_id}
    @app.get('/api/v1/demo/tokens', include_in_schema=False)
    def demo_tokens(request: Request):
        if request.app.state.settings.environment != 'development':
            raise HTTPException(404, 'Demo tokens disabled')
        from scripts.create_demo_token import make_token
        return {
            'COMPANY_A_employee': make_token('COMPANY_A', 'employee', 'demo-emp-apex'),
            'COMPANY_B_employee': make_token('COMPANY_B', 'employee', 'demo-emp-nova'),
            'COMPANY_C_employee': make_token('COMPANY_C', 'employee', 'demo-emp-vertex'),
            'COMPANY_A_admin': make_token('COMPANY_A', 'policy_admin', 'demo-admin-apex')
        }
    @app.get('/api/v1/demo/sample-policy/{version}/{format}', include_in_schema=False)
    def sample_policy(version: int, format: str, request: Request):
        policy_dir = Path(__file__).resolve().parent.parent / 'data' / 'policies'
        filename = f"COMPANY_A_v{version}.{format}"
        file_path = policy_dir / filename
        if not file_path.exists():
            from scripts.fixtures import policy_text
            content = policy_text('COMPANY_A', updated=(version == 2))
            return Response(content=content, media_type='text/plain', headers={
                'Content-Disposition': f'attachment; filename="{filename}"'
            })
        media_types = {
            'txt': 'text/plain',
            'pdf': 'application/pdf',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        }
        return FileResponse(file_path, media_type=media_types.get(format, 'text/plain'), filename=filename)
    @app.post('/api/v1/admin/demo-load-sample/{version}', response_model=Version, status_code=201)
    async def demo_load_sample(version: int, request: Request, p: Principal = Depends(admin)):
        no_tenant_query(request)
        policy_dir = Path(__file__).resolve().parent.parent / 'data' / 'policies'
        file_path = policy_dir / f"{p.company_id}_v{version}.txt"
        if file_path.exists():
            content = file_path.read_bytes()
        else:
            from scripts.fixtures import policy_text
            content = policy_text(p.company_id, updated=(version == 2)).encode('utf-8')
        return request.app.state.ingestor.ingest(p, f"{p.company_id}_v{version}.txt", content, request.state.request_id)
    frontend = Path(__file__).resolve().parent.parent/'frontend'
    @app.get('/docs', include_in_schema=False)
    def api_reference():
        return FileResponse(frontend.parent/'docs'/'api_documentation.md', media_type='text/plain')
    app.mount('/static', StaticFiles(directory=frontend, check_dir=False), name='static')
    @app.get('/', include_in_schema=False)
    def index():
        return FileResponse(frontend/'index.html')
    return app

app = create_app()
