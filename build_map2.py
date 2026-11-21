import ast, gzip, json, os, re
from coverage import CoverageData

SRC = '/workspaces/sqlglot-src'
tests = sorted(json.load(open('sample/tests.json'))['tests'], key=lambda t: t['number'])
ids = [t['id'] for t in tests]
secs = [t['seconds'] for t in tests]
num = {tid: i for i, tid in enumerate(ids)}

_cache = {}
def parse_file(path):
    if path not in _cache:
        try:
            text = open(path, encoding='utf-8').read()
            _cache[path] = (text, ast.parse(text))
        except Exception:
            _cache[path] = ('', None)
    return _cache[path]

def ftext(p):
    return parse_file(os.path.join(SRC, p))[0]

def body_of(tid):
    parts = tid.split('::')
    text, tree = parse_file(os.path.join(SRC, parts[0]))
    if tree is None:
        return ''
    name = parts[-1].split('[')[0]
    scope = tree
    for cls in parts[1:-1]:
        nxt = None
        for n in scope.body:
            if isinstance(n, ast.ClassDef) and n.name == cls.split('[')[0]:
                nxt = n
                break
        if nxt is None:
            return text
        scope = nxt
    for n in scope.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return ast.get_source_segment(text, n) or text
    return text

bodies = [body_of(t) for t in ids]
tf = {}
for i, tid in enumerate(ids):
    tf.setdefault(tid.split('::')[0], []).append(i)

# fixtures -> tests that mention them
fixroot = SRC + '/tests/fixtures'
fixfiles = []
for root, _, fs in os.walk(fixroot):
    for f in fs:
        fixfiles.append(os.path.relpath(os.path.join(root, f), fixroot))
loader_files = [p for p in tf if 'fixtures' in ftext(p) or 'load_sql_fixture' in ftext(p)]
fixdefault = sorted({i for p in loader_files for i in tf[p]})
fix = {}
for rel in fixfiles:
    base = os.path.basename(rel)
    stem = os.path.splitext(base)[0]
    pats = [rel, base, '"%s"' % stem, "'%s'" % stem]
    hit = [i for i, b in enumerate(bodies) if any(p in b for p in pats)]
    if not hit:
        hit = [i for p in tf if any(q in ftext(p) for q in pats) for i in tf[p]]
    if not hit:
        hit = fixdefault
    fix[rel] = sorted(set(hit))

# tests that look at source code / docs
rx = re.compile(r'\b(doctest|getsource|inspect|importlib|pkgutil|read_text)\b|\bast\.|sys\.modules|__all__|\blistdir\b|os\.walk')
introspect = [i for i, b in enumerate(bodies) if rx.search(b)]

# who imports whom
def modname(rel):
    m = rel[:-3].replace('/', '.')
    return m[:-9] if m.endswith('.__init__') else m
pyfiles = []
for top in ('sqlglot', 'tests'):
    for root, dirs, fs in os.walk(os.path.join(SRC, top)):
        dirs[:] = [d for d in dirs if d not in ('venv', '__pycache__', 'fixtures')]
        for f in fs:
            if f.endswith('.py'):
                pyfiles.append(os.path.relpath(os.path.join(root, f), SRC))
mod2file = {modname(p): p for p in pyfiles}
imp = {}
for p in pyfiles:
    tree = parse_file(os.path.join(SRC, p))[1]
    if tree is None:
        continue
    pkg = modname(p) if p.endswith('__init__.py') else modname(p).rpartition('.')[0]
    for n in ast.walk(tree):
        targets = []
        if isinstance(n, ast.Import):
            targets = [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            if n.level:
                parts = pkg.split('.') if pkg else []
                base = parts[:len(parts) - (n.level - 1)] if n.level - 1 <= len(parts) else []
                mod = '.'.join(base + ([n.module] if n.module else []))
            else:
                mod = n.module or ''
            targets = [mod] + [mod + '.' + a.name for a in n.names]
        for t in targets:
            f = mod2file.get(t)
            if f and f != p:
                imp.setdefault(f, set()).add(p)

# coverage -> function spans
d = CoverageData(SRC + '/.coverage')
d.read()
seen = set()
files_out = {}
for f in d.measured_files():
    line_tests = {}
    for line, ctxs in d.contexts_by_lineno(f).items():
        tn = {num[c.split('|')[0]] for c in ctxs if c.split('|')[0] in num}
        if tn:
            line_tests[line] = tn
            seen |= tn
    if not f.startswith(SRC + '/sqlglot/'):
        continue
    tree = parse_file(f)[1]
    if tree is None:
        continue
    spans = sorted((n.body[0].lineno, n.end_lineno) for n in ast.walk(tree)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    per = [set() for _ in spans]
    allf = set()
    for line, tn in line_tests.items():
        allf |= tn
        for i, (a, b) in enumerate(spans):
            if a <= line <= b:
                per[i] |= tn
    files_out[f[len(SRC) + 1:]] = {
        'spans': [[a, b, sorted(per[i])] for i, (a, b) in enumerate(spans)],
        'file': sorted(allf),
    }

always = sorted(set(range(len(ids))) - seen)
out = {'ids': ids, 'files': files_out, 'always': always, 'introspect': introspect,
       'tf': tf, 'fix': fix, 'fixdefault': fixdefault,
       'imp': {k: sorted(v) for k, v in imp.items()}}
with gzip.open('map.json.gz', 'wt') as fh:
    json.dump(out, fh, separators=(',', ':'))

def tot(s):
    return round(sum(secs[i] for i in s), 1)
print('size MB:', round(os.path.getsize('map.json.gz') / 1e6, 2), '| sqlglot files:', len(files_out))
print('always:', len(always), 'tests', tot(always), 's | introspect:', len(introspect), 'tests', tot(introspect), 's')
print('fixture-loading tests:', len(fixdefault), 'tests', tot(fixdefault), 's | fixtures mapped:', len(fix))
big = sorted(fix.items(), key=lambda kv: -tot(kv[1]))[:4]
print('biggest fixture sets:', [(k, len(v), tot(v)) for k, v in big])
