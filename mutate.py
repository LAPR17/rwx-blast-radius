import ast, json, os, random, re, subprocess, sys
SRC = '/workspaces/sqlglot-src'
RWX = '/workspaces/rwx-blast-radius'
PY = SRC + '/venv/bin/python'
random.seed(int(sys.argv[1]))
N = int(sys.argv[2])
tests = sorted(json.load(open(RWX + '/sample/tests.json'))['tests'], key=lambda t: t['number'])
ids = [t['id'] for t in tests]
num = {t['id']: t['number'] for t in tests}
def git(*a):
    return subprocess.run(['git'] + list(a), cwd=SRC, capture_output=True, text=True).stdout
files = [f for f in git('ls-files', 'sqlglot').split() if f.endswith('.py')]
rets, assigns = [], []
for f in files:
    text = open(SRC + '/' + f).read()
    try:
        tree = ast.parse(text)
    except Exception:
        continue
    L = text.split('\n')
    def walk(node, infunc):
        for ch in ast.iter_child_nodes(node):
            isf = isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef))
            if isinstance(ch, ast.Return) and ch.value is not None and ch.lineno == ch.end_lineno:
                line = L[ch.lineno - 1]
                if line.strip().startswith('return ') and line.strip() != 'return None':
                    rets.append(('return', f, ch.lineno, line[:len(line) - len(line.lstrip())] + 'return None'))
            if (not infunc and isinstance(ch, ast.Assign) and ch.lineno == ch.end_lineno
                    and len(ch.targets) == 1 and isinstance(ch.targets[0], ast.Name)):
                line = L[ch.lineno - 1]
                t = ch.targets[0].id
                if line.strip().startswith(t + ' = ') and not line.strip().endswith('None'):
                    assigns.append(('assign', f, ch.lineno, line[:len(line) - len(line.lstrip())] + t + ' = None'))
            walk(ch, infunc or isf)
    walk(tree, False)
na = max(1, N // 5)
picks = random.sample(rets, N - na) + random.sample(assigns, na)
os.makedirs('/tmp/mut/commits', exist_ok=True)
for x in os.listdir('/tmp/mut/commits'):
    os.remove('/tmp/mut/commits/' + x)
open('/tmp/mut/tests.json', 'w').write(open(RWX + '/sample/tests.json').read())
muts = {}
for k, (kind, f, ln, new) in enumerate(picks):
    cid = 'm%02d' % k
    path = SRC + '/' + f
    L = open(path).read().split('\n')
    L[ln - 1] = new
    open(path, 'w').write('\n'.join(L))
    patch = git('diff')
    git('checkout', '--', 'sqlglot')
    open('/tmp/mut/commits/%s.patch' % cid, 'w').write(patch)
    muts[cid] = (kind, f, ln, new)
out = subprocess.run(['python3', RWX + '/selector.py'], env=dict(os.environ, DATA_DIR='/tmp/mut'),
                     capture_output=True, text=True).stdout
sel = {}
for line in out.splitlines():
    r = json.loads(line)
    sel[r['commit']] = {n for w in r['workers'] for n in w}
print('selector answered', len(sel), 'of', len(muts), flush=True)
rx = re.compile(r'(tests/[\w/]+\.py(?:::[\w\[\]\-\.,]+)*)')
misses = 0
for cid, (kind, f, ln, new) in sorted(muts.items()):
    path = SRC + '/' + f
    L = open(path).read().split('\n')
    L[ln - 1] = new
    open(path, 'w').write('\n'.join(L))
    try:
        r = subprocess.run([PY, '-m', 'pytest', 'tests', '-q', '-n', '2', '-p', 'no:cacheprovider',
                            '--tb=no', '-rfE', '--timeout=120'],
                           cwd=SRC, capture_output=True, text=True, timeout=900)
        outp = r.stdout
    except subprocess.TimeoutExpired:
        outp = None
    git('checkout', '--', 'sqlglot')
    if outp is None:
        print(cid, 'timeout', flush=True)
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
                if t.startswith(tok + '::') or t.split('::')[0] == tok:
                    fail.add(num[t])
    miss = sorted(fail - sel.get(cid, set()))
    misses += bool(miss)
    print(cid, kind, f, ln, 'sel', len(sel.get(cid, ())), 'fail', len(fail),
          'MISS' if miss else 'ok', [ids[i].split('::')[-1] for i in miss[:6]], flush=True)
print('DONE', len(muts), 'mutations,', misses, 'with misses', flush=True)
