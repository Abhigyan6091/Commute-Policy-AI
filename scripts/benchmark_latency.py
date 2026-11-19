import argparse
import json
import math
import os
import platform
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx
from evaluation.dataset import CASES

def percentile(values, p):
    return sorted(values)[max(0, math.ceil(p*len(values))-1)] if values else None
def benchmark(url, token, count, concurrency):
    questions = [c['input'] for c in CASES if c['company']=='COMPANY_A' and c['status']=='answered' and not c['updated']]
    def request(i):
        start = time.perf_counter()
        try:
            with httpx.Client(base_url=url, timeout=35) as client:
                response = client.post('/api/v1/chat', headers={'Authorization':'Bearer '+token},
                    json={'question':questions[i % len(questions)]})
                body = response.json()
                success = response.status_code == 200 and body.get('status')=='answered'
                return {'latency_ms':(time.perf_counter()-start)*1000, 'success':success,
                    'http_status':response.status_code, 'timings_ms':body.get('timings_ms',{}),
                    'llm_calls':body.get('llm_calls'), 'cached':body.get('cached',False)}
        except (httpx.HTTPError, ValueError):
            return {'latency_ms':(time.perf_counter()-start)*1000, 'success':False,
                'http_status':None, 'timings_ms':{}, 'llm_calls':None, 'cached':False}
    first = request(0)
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        rows = list(pool.map(request, range(count)))
    good = [r['latency_ms'] for r in rows if r['success']]
    all_latency = [r['latency_ms'] for r in rows]
    stages = {name: statistics.mean([r['timings_ms'].get(name,0) for r in rows])
              for name in ['embedding','retrieval','llm','total']}
    return {'first_request_after_start':first, 'requests':count, 'successful':len(good), 'failed':count-len(good),
        'p50_ms':percentile(all_latency,.50), 'p95_ms':percentile(all_latency,.95), 'p99_ms':percentile(all_latency,.99),
        'average_ms':statistics.mean(all_latency), 'successful_p95_ms':percentile(good,.95),
        'average_stages_ms':stages, 'calls_per_question':[r['llm_calls'] for r in rows], 'rows':rows,
        'target_met_in_this_sample':len(good)==count and percentile(all_latency,.95)<=3000}
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--requests', type=int, default=30)
    parser.add_argument('--concurrency', type=int, default=1)
    parser.add_argument('--simulated', action='store_true', help='Benchmark in-process fake fixture instead')
    parser.add_argument('--conditions', required=True, help='CPU, RAM, provider/model, region/network, cache and rate-limit settings')
    args = parser.parse_args()
    if args.requests < 1 or args.concurrency < 1:
        parser.error('Counts must be positive')
    if args.simulated:
        from scripts.run_evaluation import run
        _, details, metrics = run()
        result = {'execution':'SIMULATED FAKE LLM; not a real latency qualification', 'details':details, 'metrics':metrics}
    else:
        token = os.environ.get('BENCHMARK_TOKEN')
        if not token:
            parser.error('Set BENCHMARK_TOKEN to a Company A employee token')
        result = benchmark(args.url, token, args.requests, args.concurrency)
        result['execution'] = 'LIVE HTTP; operator must confirm configured real provider and disable cache'
        if any(r['cached'] or r['llm_calls'] != 1 for r in result['rows']):
            result['target_met_in_this_sample'] = False
            result['qualification'] = 'Not every request was an uncached single-provider-call answer; inspect failures/corrections.'
    result.update({'conditions':args.conditions, 'platform':platform.platform(), 'concurrency':args.concurrency,
        'cold_start_note':'Embedding startup is outside request timing. Restart before measuring first request; first request is not a model-download cold-start measurement.'})
    Path('evaluation').mkdir(exist_ok=True)
    Path('evaluation/latency_benchmark.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
if __name__ == '__main__':
    main()
