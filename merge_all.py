import gzip, json, os, sys
from coverage import CoverageData
if 'ALL DONE' not in open('/tmp/iso_all.log').read():
    print('NOT FINISHED YET - wait and run again'); sys.exit(1)
SRC = '/workspaces/sqlglot-src'
M = json.load(gzip.open('map.json.gz', 'rt'))
ids = M['ids']
ok = []
for i in range(len(ids)):
    p = '/tmp/iso/%d.cov' % i
    if os.path.exists(p):
        try:
            CoverageData(p).read()
            ok.append(i)
        except Exception:
            pass
S = set(ok)
fs = {}
for rel, e in M['files'].items():
    l2s = {}
    for k, (a, b, _) in enumerate(e['spans']):
        for ln in range(a, b + 1):
            l2s.setdefault(ln, []).append(k)
    fs[rel] = (l2s, {n for n in e['file'] if n not in S}, [{n for n in sp[2] if n not in S} for sp in e['spans']])
for i in ok:
    d = CoverageData('/tmp/iso/%d.cov' % i)
    d.read()
    for f in d.measured_files():
        rel = f[len(SRC) + 1:]
        if rel not in fs:
            continue
        l2s, fset, per = fs[rel]
        lines = list(d.contexts_by_lineno(f).keys())
        if not lines:
            continue
        fset.add(i)
        for ln in lines:
            for k in l2s.get(ln, ()):
                per[k].add(i)
os.system('cp map.json.gz /tmp/map_before_merge.json.gz')
for rel, e in M['files'].items():
    l2s, fset, per = fs[rel]
    e['file'] = sorted(fset)
    for k, sp in enumerate(e['spans']):
        sp[2] = sorted(per[k])
with gzip.open('map.json.gz', 'wt') as fh:
    json.dump(M, fh, separators=(',', ':'))
missing = [i for i in range(len(ids)) if i not in S]
print('merged', len(ok), 'of', len(ids), '| no recording:', len(missing), [ids[i].split('::')[-1] for i in missing[:8]])
print('size MB:', round(os.path.getsize('map.json.gz') / 1e6, 2))
