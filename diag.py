import json
ans = json.load(open('sample/answers.json'))['commits']
tests = {t['number']: t for t in json.load(open('sample/tests.json'))['tests']}
rows, total, misses = [], 0, 0
for line in open('output.jsonl'):
    r = json.loads(line)
    ws = [w for w in r['workers'] if w]
    sel = {n for w in ws for n in w}
    cost = (max(sum(round(tests[n]['seconds'] * 1000) for n in w) for w in ws) + 2000 * len(ws)) / 1000 if ws else 0
    a = ans[r['commit']]
    miss = [n for n in a['failing'] if n not in sel]
    total += cost
    misses += bool(miss)
    rows.append((cost, r['commit'], a['kind'], len(sel), len(a['failing']), miss))
for cost, c, k, ns, nf, miss in sorted(rows, reverse=True):
    print(c, k, 'cost %.1f' % cost, 'selected', ns, 'failing', nf, 'MISSED' if miss else '')
    for n in miss:
        print('     missed:', tests[n]['id'])
print('TOTAL simulated %.1f s, misses %d' % (total + 300 * misses, misses))