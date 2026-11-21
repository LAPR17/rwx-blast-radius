import json
T = json.load(open('sample/tests.json'))['tests']
o = [t for t in T if t['id'].startswith(('tests/test_optimizer.py', 'tests/test_executor.py'))]
o.sort(key=lambda t: -t['seconds'])
print(len(o), round(sum(t['seconds'] for t in o), 1))
for t in o[:8]:
    print(round(t['seconds'], 1), t['id'].split('::')[-1])