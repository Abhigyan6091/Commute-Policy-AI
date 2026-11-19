import re
import time
from collections import OrderedDict, deque
from threading import Lock
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from app.schemas import Principal

bearer = HTTPBearer(auto_error=False)
INJECTION = re.compile(r'(ignore\s+(?:all|previous|system)|reveal\s+(?:all|other)|AI\s+SYSTEM|system\s+prompt|developer\s+message)', re.I)
def suspicious(text):
    return bool(INJECTION.search(text))

def decode_token(token, settings):
    claims = jwt.decode(token, settings.jwt_secret.get_secret_value(),
        algorithms=[settings.jwt_algorithm], issuer=settings.jwt_issuer, audience=settings.jwt_audience,
        options={'require': ['user_id','employee_id','company_id','role','exp','iat','iss','aud']})
    if isinstance(claims['iat'], bool) or isinstance(claims['exp'], bool):
        raise ValueError('Invalid time claims')
    if not isinstance(claims['iat'], (int, float)) or not isinstance(claims['exp'], (int, float)):
        raise ValueError('Invalid time claims')
    if claims['exp'] <= claims['iat']:
        raise ValueError('Invalid token lifetime')
    return Principal.model_validate({k: claims[k] for k in Principal.model_fields})

def principal(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    try:
        if credentials is None or credentials.scheme.lower() != 'bearer':
            raise ValueError('Missing credentials')
        return decode_token(credentials.credentials, request.app.state.settings)
    except (jwt.InvalidTokenError, ValidationError, ValueError, KeyError, TypeError):
        raise HTTPException(401, 'Invalid or expired credentials', headers={'WWW-Authenticate': 'Bearer'}) from None

def admin(p: Principal = Depends(principal)):
    if p.role != 'policy_admin':
        raise HTTPException(403, 'Policy administrator role required')
    return p

class RateLimiter:
    def __init__(self, limit):
        self.limit, self.entries, self.lock = limit, OrderedDict(), Lock()
    def check(self, company, user):
        now = time.monotonic()
        with self.lock:
            stale = [key for key, q in self.entries.items() if not q or now - q[-1] >= 60]
            for key in stale:
                del self.entries[key]
            key = (company, user)
            if key not in self.entries and len(self.entries) >= 10000:
                raise HTTPException(429, 'Service rate limit reached', headers={'Retry-After': '60'})
            queue = self.entries.setdefault(key, deque())
            while queue and now - queue[0] >= 60:
                queue.popleft()
            if len(queue) >= self.limit:
                raise HTTPException(429, 'Rate limit reached', headers={'Retry-After': '60'})
            queue.append(now)

class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app
    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('method') not in ('POST', 'PUT', 'PATCH'):
            return await self.app(scope, receive, send)
        from starlette.responses import JSONResponse
        from uuid import uuid4
        cfg = scope['app'].state.settings
        limit = cfg.max_upload_bytes + 65536 if scope['path'] == '/api/v1/admin/policies/upload' else 16384
        request_id = scope.get('state', {}).get('request_id', uuid4().hex)
        headers = dict(scope.get('headers', []))
        async def reject(code, detail):
            response = JSONResponse({'detail': detail, 'request_id': request_id}, status_code=code)
            await response(scope, receive, send)
        try:
            length = int(headers.get(b'content-length', b'0'))
            if length < 0:
                raise ValueError('Negative content length')
        except ValueError:
            return await reject(400, 'Invalid content length')
        if length > limit:
            return await reject(413, 'Request body exceeds size limit')
        parts, size = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            part = message.get('body', b'')
            size += len(part)
            if size > limit:
                return await reject(413, 'Request body exceeds size limit')
            parts.append(part)
            if not message.get('more_body', False):
                break
        body, delivered = b''.join(parts), False
        async def replay():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {'type': 'http.request', 'body': body, 'more_body': False}
        await self.app(scope, replay, send)
