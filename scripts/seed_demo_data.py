import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from uuid import uuid4
import httpx
from scripts.fixtures import COMPANIES, policy_text

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--write-only', action='store_true')
    args = parser.parse_args()
    from scripts.create_demo_token import make_token
    for company in COMPANIES:
        path = Path('data/policies') / f'{company}_v1.txt'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(policy_text(company), encoding='utf-8')
        if args.write_only:
            continue
        token = make_token(company, 'policy_admin', 'seed-'+uuid4().hex[:8])
        headers = {'Authorization': 'Bearer '+token}
        with httpx.Client(base_url=args.url, timeout=120) as client:
            current = client.get('/api/v1/admin/policies/current', headers=headers)
            if current.status_code == 200:
                print(company, 'already has an active policy; skipped')
                continue
            if current.status_code != 404:
                current.raise_for_status()
            response = client.post('/api/v1/admin/policies/upload', headers=headers,
                files={'file': (path.name, path.read_bytes(), 'text/plain')})
            response.raise_for_status()
            print(company, response.json()['id'])
    Path('data/policies/COMPANY_A_v2.txt').write_text(policy_text('COMPANY_A', updated=True), encoding='utf-8')
if __name__ == '__main__':
    main()
