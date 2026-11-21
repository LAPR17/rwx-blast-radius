import json
import re

ans = json.load(open('sample/answers.json'))['commits']
tests = {t['number']: t['id'] for t in json.load(open('sample/tests.json'))['tests']}
target = [n for n, i in tests.items() if i.endswith('test_execute_tpcds')]
print('test numbers:', target)
for c, a in sorted(ans.items()):
    if any(n in target for n in a['failing']):
        text = open('sample/commits/%s.patch' % c).read()
        files = re.findall(r'^diff --git a/(\S+)', text, re.M)
        print(c, a['kind'], files)
        