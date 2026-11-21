"""Blast Radius selector: coverage map + import map + fixture map built from the pinned commit."""
import gzip
import json
import os
import re
import sys
from pathlib import Path

DATA = Path(os.environ.get("DATA_DIR", "/data"))
HERE = Path(__file__).resolve().parent
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
FIXDIR = "tests/fixtures/"


def clean(p):
    p = p.split("\t")[0].strip().strip('"')
    if p == "/dev/null":
        return None
    if p.startswith(("a/", "b/")):
        return p[2:]
    return p


def parse_patch(text):
    files, cur = [], None
    rem_old = rem_new = 0
    old_ln = 0

    def fresh():
        d = {"old": None, "new": None, "lines": set(), "texts": [], "hunks": 0, "seen_old": False}
        files.append(d)
        return d

    for line in text.split("\n"):
        if rem_old > 0 or rem_new > 0:
            if line.startswith("\\"):
                continue
            c = line[:1]
            if c == "+":
                cur["lines"].update((old_ln - 1, old_ln))
                cur["texts"].append(line[1:])
                rem_new -= 1
            elif c == "-":
                cur["lines"].add(old_ln)
                cur["texts"].append(line[1:])
                old_ln += 1
                rem_old -= 1
            else:
                old_ln += 1
                rem_old -= 1
                rem_new -= 1
            continue
        if line.startswith("diff --git "):
            cur = fresh()
            m = re.match(r'diff --git "?a/(.*?)"? "?b/(.*?)"?$', line)
            if m:
                cur["old"], cur["new"] = m.group(1), m.group(2)
        elif line.startswith("--- "):
            if cur is None or cur["hunks"] or cur["seen_old"]:
                cur = fresh()
            cur["seen_old"] = True
            cur["old"] = clean(line[4:])
        elif line.startswith("+++ "):
            if cur is None:
                cur = fresh()
            cur["new"] = clean(line[4:])
        elif line.startswith("rename from ") and cur is not None:
            cur["old"] = line[12:].strip()
        elif line.startswith("rename to ") and cur is not None:
            cur["new"] = line[10:].strip()
        elif line.startswith("@@") and cur is not None:
            m = HUNK.match(line)
            if m:
                a = int(m.group(1))
                b = int(m.group(2)) if m.group(2) is not None else 1
                dd = int(m.group(4)) if m.group(4) is not None else 1
                rem_old, rem_new = b, dd
                old_ln = a + 1 if b == 0 else a
                cur["hunks"] += 1
    return files


def pack(items):
    """items: list of (number, milliseconds). Best split over 1..8 workers."""
    if not items:
        return []
    items = sorted(items, key=lambda x: -x[1])
    best = None
    for k in range(1, min(8, len(items)) + 1):
        loads = [0] * k
        ws = [[] for _ in range(k)]
        for n, ms in items:
            i = loads.index(min(loads))
            ws[i].append(n)
            loads[i] += ms
        cost = max(loads) + 2000 * k
        if best is None or cost < best[0]:
            best = (cost, ws)
    return best[1]


def main():
    M = json.load(gzip.open(HERE / "map.json.gz", "rt"))
    rt = json.loads((DATA / "tests.json").read_text())["tests"]
    by_id = {t["id"]: t for t in rt}
    mids = M["ids"]
    known = set(mids)
    idx_num = [by_id[i]["number"] if i in by_id else -1 for i in mids]
    idx_ms = [round(by_id[i]["seconds"] * 1000) if i in by_id else 0 for i in mids]
    extra = [(t["number"], round(t["seconds"] * 1000)) for t in rt if t["id"] not in known]
    ALL = set(range(len(mids)))
    always = set(M["always"])
    intro = set(M["introspect"]) | always
    files, imp, tf, fix = M["files"], M["imp"], M["tf"], M["fix"]
    fixdefault = set(M["fixdefault"])
    opt = set(tf.get("tests/test_optimizer.py", ())) | set(tf.get("tests/test_executor.py", ()))

    def filelevel(q):
        if q in files:
            return set(files[q]["file"])
        return set(tf.get(q, ()))

    def tests_for(path):
        seen, stack, out = set(), [path], set()
        while stack:
            p = stack.pop()
            if p in seen:
                continue
            seen.add(p)
            out.update(tf.get(p, ()))
            for q in imp.get(p, ()):
                if q.startswith("tests/"):
                    stack.append(q)
        if os.path.basename(path) == "conftest.py" or path == "tests/__init__.py":
            out |= ALL
        if not out:
            out |= always
        return out

    def handle(f, path):
        texts = f["texts"]
        is_py = path.endswith(".py")
        comment_only = bool(is_py and f["lines"] and texts and
                            all((not t.strip()) or t.strip().startswith("#") for t in texts))
        marks = any(('"""' in t) or ("'''" in t) or (">>>" in t) for t in texts)
        if path.startswith(FIXDIR):
            key = path[len(FIXDIR):]
            return set(ALL)
        if path.startswith("tests/") and is_py:
            return set(intro) if comment_only else tests_for(path)
        if path.startswith("sqlglot/") and is_py:
            if comment_only:
                return set(intro)
            e = files.get(path)
            out = set()
            if e is None:
                out |= intro
                for q in imp.get(path, ()):
                    out |= filelevel(q)
                return out
            outside = not f["lines"]
            for ln in f["lines"]:
                best = None
                for a, b, ts in e["spans"]:
                    if a <= ln <= b and (best is None or b - a < best[1] - best[0]):
                        best = (a, b, ts)
                if best is None:
                    outside = True
                else:
                    out.update(best[2])
            if True:
                out |= set(e["file"])
                for q in imp.get(path, ()):
                    out |= filelevel(q)
            if marks:
                out |= intro
            return out
        low = path.lower()
        if path.startswith(("docs/", ".github/")) or low.endswith((".md", ".rst")):
            return set(intro)
        return set(ALL)

    def choose(text):
        sel = set()
        touched_py = False
        for f in parse_patch(text):
            path = f["old"] or f["new"]
            if path is None:
                return set(ALL)
            if path.endswith(".py"):
                touched_py = True
            sel |= handle(f, path)
            if path.startswith("sqlglot/") and path.endswith(".py"):
                sel |= (opt & set(files[path]["file"]) if path in files else opt)
        if touched_py:
            sel |= always
        return sel

    total = 0
    for patch in sorted((DATA / "commits").glob("*.patch")):
        try:
            sel = choose(patch.read_text(errors="replace"))
        except Exception as exc:
            print("fallback to all tests for", patch.stem, exc, file=sys.stderr)
            sel = set(ALL)
        items = [(idx_num[i], idx_ms[i]) for i in sel if idx_num[i] >= 0]
        if sel:
            items += extra
        total += len(items)
        print(json.dumps({"commit": patch.stem, "workers": pack(items)}))
    print("selected", total, "tests in total", file=sys.stderr)


if __name__ == "__main__":
    main()
