import secrets
import time
from uuid import uuid4
import jwt
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.retrieval import FakeEmbedder
from scripts.fixtures import COMPANIES, FakeLLM, identity, policy_text

def token(settings, company='COMPANY_A', role='employee', user='tester', **overrides):
    now = int(time.time())
    claims = {**identity(company, user=user).model_dump(), 'role':role, 'iat':now, 'exp':now+3600,
        'iss':settings.jwt_issuer, 'aud':settings.jwt_audience, **overrides}
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm='HS256')

@pytest.fixture
def cfg(tmp_path):
    return Settings(environment='test', jwt_secret=secrets.token_urlsafe(48), data_dir=tmp_path,
        embedding_model='offline-hash-256-v1', relevance_threshold=0.05, request_deadline=30, requests_per_minute=10000)

@pytest.fixture
def system(cfg):
    app = create_app(cfg, FakeEmbedder(), FakeLLM())
    with TestClient(app) as client:
        for company in COMPANIES:
            app.state.ingestor.ingest(identity(company, 'policy_admin'), f'{company}.txt', policy_text(company).encode(), uuid4().hex)
        yield app, client

def headers(cfg, company='COMPANY_A', role='employee', **claims):
    return {'Authorization':'Bearer '+token(cfg,company,role,**claims)}
