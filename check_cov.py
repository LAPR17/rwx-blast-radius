import json
from coverage import CoverageData
tests = json.load(open('sample/tests.json'))['tests']
ids = {t['id'] for t in tests}
d = CoverageData('/workspaces/sqlglot-src/.coverage')
d.read()
files = d.measured_files()
ctx = set()
for f in files:
    for line, cs in d.contexts_by_lineno(f).items():
        ctx.update(cs)
clean = {c.split('|')[0] for c in ctx if c}
print(len(files), 'source files;', len(clean), 'contexts;', len(clean & ids), 'match tests.json;', len(ids - clean), 'tests never seen')
print('unmatched contexts sample:', sorted(clean - ids)[:5])
print('unseen tests sample:', sorted(ids - clean)[:5])
