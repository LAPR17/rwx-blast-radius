import gzip, json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
SRC = '/workspaces/sqlglot-src'
PY = SRC + '/venv/bin/python'
ids = json.load(gzip.open('/workspaces/rwx-blast-radius/map.json.gz', 'rt'))['ids']
todo = list(range(len(ids)))
os.makedirs('/tmp/iso', exist_ok=True)
def run(i):
    cov = '/tmp/iso/%d.cov' % i
    if os.path.exists(cov):
        return
    env = dict(os.environ, COVERAGE_FILE=cov + '.part', COVERAGE_CORE='ctrace')
    try:
        subprocess.run([PY, '-m', 'pytest', ids[i], '-q', '-p', 'no:cacheprovider', '--cov=sqlglot', '--cov-report='],
                       cwd=SRC, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    except Exception:
        pass
    if os.path.exists(cov + '.part'):
        os.rename(cov + '.part', cov)
with ThreadPoolExecutor(2) as ex:
    for k, _ in enumerate(ex.map(run, todo)):
        if k % 50 == 0:
            print('done', k, 'of', len(todo), flush=True)
print('ALL DONE', flush=True)
