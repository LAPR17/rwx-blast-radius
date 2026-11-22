import json, ast, gzip, os
from coverage import CoverageData

SRC = '/workspaces/sqlglot-src'
tests = json.load(open('sample/tests.json'))['tests']
num = {t['id']: t['number'] for t in tests}
secs = {t['number']: t['seconds'] for t in tests}
ids = {t['number']: t['id'] for t in tests}

d = CoverageData(SRC + '/.coverage')
d.read()

seen = set()
files_out = {}
n_spans = 0
n_ints = 0
for f in d.measured_files():
    by_line = d.contexts_by_lineno(f)
    line_tests = {}
    for line, ctxs in by_line.items():
        tn = {num[c.split('|')[0]] for c in ctxs if c.split('|')[0] in num}
        if tn:
            line_tests[line] = tn
            seen |= tn
    if not f.startswith(SRC + '/sqlglot/'):
        continue
    rel = f[len(SRC) + 1:]
    try:
        tree = ast.parse(open(f).read())
    except Exception as e:
        print('skip', rel, e)
        continue
    spans = sorted((n.body[0].lineno, n.end_lineno) for n in ast.walk(tree)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    per = [set() for _ in spans]
    allf = set()
    for line, tn in line_tests.items():
        allf |= tn
        for i, (a, b) in enumerate(spans):
            if a <= line <= b:
                per[i] |= tn
    files_out[rel] = {
        'spans': [[a, b, sorted(per[i])] for i, (a, b) in enumerate(spans)],
        'file': sorted(allf),
    }
    n_spans += len(spans)
    n_ints += len(allf) + sum(len(p) for p in per)

always = sorted(set(secs) - seen)
out = {'files': files_out, 'always': always}
with gzip.open('map.json.gz', 'wt') as fh:
    json.dump(out, fh, separators=(',', ':'))

print(len(files_out), 'files;', n_spans, 'functions;', n_ints, 'numbers stored')
print('map.json.gz size (MB):', round(os.path.getsize('map.json.gz') / 1e6, 2))
print('always-include tests:', [(n, ids[n].split('::')[-1], secs[n]) for n in always])
