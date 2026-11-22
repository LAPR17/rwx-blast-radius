import json, collections, re, pathlib
t = json.load(open('sample/tests.json'))['tests']
a = json.load(open('sample/answers.json'))['commits']
print(len(t), 'tests,', round(sum(x['seconds'] for x in t), 1), 'seconds total')
print(collections.Counter(v['kind'] for v in a.values()))
for cid, v in sorted(a.items()):
    p = pathlib.Path('sample/commits') / (cid + '.patch')
    files = re.findall(r'^\+\+\+ b/(\S+)', p.read_text(), re.M)
    print(cid, v['kind'], len(v['failing']), 'failing', files)
