import json, gzip, sys
sys.path.insert(0, '.')
import selector as S
M = json.load(gzip.open('map.json.gz', 'rt'))
tests = json.load(open('sample/tests.json'))['tests']
sec = {t['number']: t['seconds'] for t in tests}
tid = {t['number']: t['id'] for t in tests}
ans = json.load(open('sample/answers.json'))['commits']
sel = {}
for line in open('output.jsonl'):
    r = json.loads(line)
    sel[r['commit']] = {n for w in r['workers'] for n in w}
def tot(f):
    return round(sum(t['seconds'] for t in tests if f in t['file']), 1)
print('seconds: test_optimizer.py', tot('tests/test_optimizer.py'), '| test_executor.py', tot('tests/test_executor.py'))
print('slowest:', [(tid[n].split('::')[-1], sec[n]) for n in sorted(sec, key=lambda k: -sec[k])[:8]])
for c, ans_c in sorted(ans.items()):
    miss = [n for n in ans_c['failing'] if n not in sel[c]]
    if not miss:
        continue
    print('==', c, ans_c['kind'], 'missed', [(tid[n].split('::')[-1], sec[n]) for n in miss])
    for f in S.parse_patch(open('sample/commits/%s.patch' % c).read()):
        path = f['old'] or f['new']
        e = M['files'].get(path)
        print('  file', path, 'changed lines', sorted(f['lines'])[:10], 'in map:', e is not None)
        if e:
            print('  missed tests covered anywhere in file:', [n in set(e['file']) for n in miss])
            for ln in sorted(f['lines'])[:5]:
                sp = [(x, y, [n in ts for n in miss]) for x, y, ts in e['spans'] if x <= ln <= y]
                print('   line', ln, 'enclosing spans (start, end, missed-in-span):', sp[:3])
