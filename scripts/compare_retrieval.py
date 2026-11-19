import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.run_evaluation import run

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--real', action='store_true')
    args = parser.parse_args()
    results = {mode: run(mode, args.real) for mode in ['dense','hybrid']}
    if [r['id'] for r in results['dense'][0]] != [r['id'] for r in results['hybrid'][0]]:
        raise ValueError('Comparison dataset mismatch')
    regressions = [a['id'] for a,b in zip(results['dense'][1],results['hybrid'][1]) if a['pass'] and not b['pass']]
    deltas = {k: results['hybrid'][2][k]-results['dense'][2][k] for k in ['hit1','hit3','recall3','rr','retrieval_ms','total_ms','context_chars']}
    improved = deltas['hit3'] > 0 or deltas['rr'] > 0
    report = {'execution': 'real provider' if args.real else 'simulated', 'dense': results['dense'][2],
        'hybrid': results['hybrid'][2], 'deltas': deltas, 'regressions': regressions,
        'conclusion': 'Improved at least one retrieval metric; inspect regressions.' if improved else 'No measured retrieval improvement on this dataset.'}
    Path('evaluation').mkdir(exist_ok=True)
    Path('evaluation/retrieval_comparison.json').write_text(json.dumps({'summary': report, 'runs': results}, indent=2), encoding='utf-8')
    Path('evaluation/retrieval_comparison.md').write_text('# Dense versus hybrid\n\n'+
        json.dumps(report, indent=2)+'\n\nHybrid adds a bounded BM25 index and RRF merging per tenant/version. '+
        'BM25 has O(N) lexical scoring and stores token statistics in memory; the index cache holds at most 24 versions. '+
        'The dense relevance gate applies in both modes. Repeated runs and human semantic review are required. '+
        'Hash-embedding results do not establish real MiniLM retrieval quality.', encoding='utf-8')
    print(json.dumps(report, indent=2))
if __name__ == '__main__':
    main()
