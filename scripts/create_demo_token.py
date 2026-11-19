import argparse
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import jwt
from app.config import Settings
from app.schemas import Principal

def make_token(company, role='employee', user='demo'):
    settings = Settings()
    if settings.environment != 'development':
        raise RuntimeError('Demo token generation is development-only')
    p = Principal(user_id=user, employee_id=user, company_id=company, role=role)
    now = int(time.time())
    return jwt.encode({**p.model_dump(), 'iat': now, 'exp': now+3600,
        'iss': settings.jwt_issuer, 'aud': settings.jwt_audience},
        settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--company', required=True, choices=['COMPANY_A','COMPANY_B','COMPANY_C'])
    parser.add_argument('--role', choices=['employee','policy_admin'], default='employee')
    parser.add_argument('--user', default='demo')
    args = parser.parse_args()
    print(make_token(args.company, args.role, args.user))
