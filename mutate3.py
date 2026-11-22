import ast, json, os, random, re, subprocess, sys
SRC = '/workspaces/sqlglot-src'
RWX = '/workspaces/rwx-blast-radius'
PY = SRC + '/venv/bin/python'
random.seed(int(sys.argv[1]))
K = int(sys.argv[2])
tests = sorted(json.load(open(RWX + '/sample/tests.json'))['tests'], key=lambda t: t['number'])
ids = [t['id'] for t in tests]
num = {t['id']: t['number'] for t in tests}
def git(*a):
    return subprocess.run(['git'] + list(a), cwd=SRC, capture_output=True, text=True).stdout
git('checkout', '--', 'sqlglot', 'tests')
cands = {k: [] for k in ('insert', 'delete', 'comment', 'docstring', 'signature', 'testedit', 'fixture')}
srcfiles = [f for f in git('ls-files', 'sqlglot').split() if f.endswith('.py')]
testfiles = [f for f in git('ls-files', 'tests').split() if f.endswith('.py')]
fixfiles = [f for f in git('ls-files', 'tests/fixtures/optimizer').split() if f.endswith('.sql')]
def parse(f):
    text = open(SRC + '/' + f).read()
    try:
        return text.split('\n'), ast.parse(text)
    except Exception:
        return None, None
for f in srcfiles:
    L, tree = parse(f)
    if tree is None:
        continue
    for n in ast.walk(tree):
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        b0 = n.body[0]
        pad = ' ' * b0.col_offset
        doc = isinstance(b0, ast.Expr) and isinstance(b0.value, ast.Constant) and isinstance(b0.value.value, str)
        if b0.lineno > n.lineno and not doc:
            cands['insert'].append((f, 'ins', b0.lineno - 1, pad + 'raise RuntimeError("mut")'))
            cands['comment'].append((f, 'ins', b0.lineno - 1, pad + '# mut'))
        if doc and b0.lineno == b0.end_lineno and L[b0.lineno - 1].rstrip().endswith('"""'):
            cands['docstring'].append((f, 'rep', b0.lineno - 1, L[b0.lineno - 1].rstrip()[:-3] + ' mut"""'))
        if len(n.body) >= 3:
            for st in n.body[1:]:
                ok = isinstance(st, (ast.Assign, ast.AugAssign)) or (
                    isinstance(st, ast.Expr) and not isinstance(st.value, ast.Constant))
                if ok and st.lineno == st.end_lineno:
                    cands['delete'].append((f, 'del', st.lineno - 1, None))
        dl = L[n.lineno - 1]
        if dl.rstrip().endswith(':') and re.search(r'=\s*(True|False)', dl):
            new = re.sub(r'=\s*(True|False)', lambda m: m.group(0).replace(m.group(1), 'False' if m.group(1) == 'True' else 'True'), dl, count=1)
            cands['signature'].append((f, 'rep', n.lineno - 1, new))
for f in testfiles:
    L, tree = parse(f)
    if tree is None:
        continue
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name.startswith('test_') and n.args.args and n.args.args[0].arg == 'self':
            b0 = n.body[0]
            if b0.lineno > n.lineno:
                cands['testedit'].append((f, 'ins', b0.lineno - 1, ' ' * b0.col_offset + 'self.fail("mut")'))
for f in fixfiles:
    L = open(SRC + '/' + f).read().split('\n')
    for i, l in enumerate(L):
        s = l.strip()
        if s and not s.startswith('#') and s != ';':
            cands['fixture'].append((f, 'del', i, None))
picks = []
for kind, c in cands.items():
    if kind not in os.environ.get('KINDS', ','.join(cands)).split(','):
        continue
    print(kind, len(c), 'candidates', flush=True)
    for p in random.sample(c, min(K, len(c))):
        picks.append((kind,) + p)
def apply(path, op, idx, text):
    p = SRC + '/' + path
    L = open(p).read().split('\n')
    if op == 'ins':
        L.insert(idx, text)
    elif op == 'rep':
        L[idx] = text
    else:
        del L[idx]
    open(p, 'w').write('\n'.join(L))
os.makedirs('/tmp/mut/commits', exist_ok=True)
for x in os.listdir('/tmp/mut/commits'):
    os.remove('/tmp/mut/commits/' + x)
open('/tmp/mut/tests.json', 'w').write(open(RWX + '/sample/tests.json').read())
muts = {}
for k, (kind, f, op, idx, text) in enumerate(picks):
    cid = 'm%02d' % k
    apply(f, op, idx, text)
    patch = git('diff')
    git('checkout', '--', 'sqlglot', 'tests')
    open('/tmp/mut/commits/%s.patch' % cid, 'w').write(patch)
    muts[cid] = (kind, f, op, idx, text)
out = subprocess.run(['python3', RWX + '/selector.py'], env=dict(os.environ, DATA_DIR='/tmp/mut'),
                     capture_output=True, text=True).stdout
sel = {}
for line in out.splitlines():
    r = json.loads(line)
    sel[r['commit']] = {n for w in r['workers'] for n in w}
print('selector answered', len(sel), 'of', len(muts), flush=True)
rx = re.compile(r'(tests/[\w/]+\.py(?:::[\w\[\]\-\.,]+)*)')
misses = 0
for cid, (kind, f, op, idx, text) in sorted(muts.items()):
    apply(f, op, idx, text)
    try:
        r = subprocess.run([PY, '-m', 'pytest', 'tests', '-q', '-n', '2', '-p', 'no:cacheprovider',
                            '--tb=no', '-rfE', '--timeout=120'],
                           cwd=SRC, capture_output=True, text=True, timeout=900)
        outp = r.stdout
    except subprocess.TimeoutExpired:
        outp = None
    git('checkout', '--', 'sqlglot', 'tests')
    if outp is None:
        print(cid, kind, 'timeout', flush=True)
        continue
    fail = set()
    for line in outp.splitlines():
        if not line.startswith(('FAILED', 'ERROR', 'SUB')):
            continue
        m = rx.search(line)
        if not m:
            continue
        tok = m.group(1)
        if tok in num:
            fail.add(num[tok])
        else:
            for t in ids:
                if t.split('::')[0] == tok or t.startswith(tok + '::'):
                    fail.add(num[t])
    miss = sorted(fail - sel.get(cid, set()))
    misses += bool(miss)
    print(cid, kind, f, idx + 1, 'sel', len(sel.get(cid, ())), 'fail', len(fail),
          'MISS' if miss else 'ok', [ids[i].split('::')[-1] for i in miss[:6]], flush=True)
print('DONE', len(muts), 'mutations,', misses, 'with misses', flush=True)
