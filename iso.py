import gzip, json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from coverage import CoverageData
SRC = '/workspaces/sqlglot-src'
PY = SRC + '/venv/bin/python'
M = json.load(gzip.open('map.json.gz', 'rt'))
ids = M['ids']
todo = [i for i, t in enumerate(ids) if t.startswith(('tests/test_optimizer.py', 'tests/test_executor.py'))]
os.makedirs('/tmp/iso', exist_ok=True)
def run(i):
    cov = '/tmp/iso/%d.cov' % i
    if os.path.exists(cov):
        os.remove(cov)
    env = dict(os.environ, COVERAGE_FILE=cov, COVERAGE_CORE='ctrace')
    subprocess.run([PY, '-m', 'pytest', ids[i], '-q', '-p', 'no:cacheprovider', '--cov=sqlglot', '--cov-report='],
                   cwd=SRC, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return i
with ThreadPoolExecutor(2) as ex:
    for k, _ in enumerate(ex.map(run, todo)):
        if k % 10 == 0:
            print('recorded', k, 'of', len(todo), file=sys.stderr)
S = set(todo)
for e in M['files'].values():
    e['file'] = [n for n in e['file'] if n not in S]
    for sp in e['spans']:
        sp[2] = [n for n in sp[2] if n not in S]
added = 0
for i in todo:
    d = CoverageData('/tmp/iso/%d.cov' % i)
    try:
        d.read()
    except Exception:
        print('no data for', ids[i], file=sys.stderr)
        continue
    for f in d.measured_files():
        rel = f[len(SRC) + 1:]
        e = M['files'].get(rel)
        if e is None:
            continue
        lines = list(d.contexts_by_lineno(f).keys())
        if not lines:
            continue
        e['file'] = sorted(set(e['file']) | {i})
        for sp in e['spans']:
            if any(sp[0] <= ln <= sp[1] for ln in lines):
                sp[2] = sorted(set(sp[2]) | {i})
        added += 1
with gzip.open('map.json.gz', 'wt') as fh:
    json.dump(M, fh, separators=(',', ':'))
n = ids.index('tests/test_optimizer.py::TestOptimizer::test_tpch')
print('re-recorded', len(todo), 'tests; file entries added:', added)
print('test_tpch now linked to eliminate_joins.py:', n in M['files']['sqlglot/optimizer/eliminate_joins.py']['file'])
