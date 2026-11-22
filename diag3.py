import json, gzip
from coverage import CoverageData
d = CoverageData('/tmp/one.cov')
d.read()
hit = 0
for f in d.measured_files():
    if f.endswith('optimizer/eliminate_joins.py'):
        hit = len(d.contexts_by_lineno(f))
print('single run: lines of eliminate_joins.py reached by test_tpch:', hit)
M = json.load(gzip.open('map.json.gz', 'rt'))
n = M['ids'].index('tests/test_optimizer.py::TestOptimizer::test_tpch')
e = M['files']['sqlglot/optimizer/eliminate_joins.py']
print('full map links test_tpch to this file:', n in e['file'])
print('tests the map links to this file:', len(e['file']))
