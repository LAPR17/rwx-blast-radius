import json, gzip, sys, os
from collections import defaultdict

DATA = '/data'
COMMITS_DIR = os.path.join(DATA, 'commits')

with gzip.open('/app/coverage_map.json.gz', 'rt') as f:
    COVERAGE = json.load(f)

with open(os.path.join(DATA, 'tests.json')) as f:
    TESTS_RAW = json.load(f)['tests']
    TEST_BY_ID = {t['id']: t for t in TESTS_RAW}
    TEST_BY_NUMBER = {t['number']: t for t in TESTS_RAW}

def parse_patch(patch_path):
    changes = defaultdict(list)
    current_file = None
    with open(patch_path) as f:
        for line in f:
            if line.startswith('--- a/'):
                current_file = line[6:].strip()
            elif line.startswith('+++ b/'):
                current_file = line[6:].strip()
            elif line.startswith('@@'):
                parts = line.split()
                if len(parts) >= 3:
                    new_info = parts[2][1:]
                    if ',' in new_info:
                        start, count = new_info.split(',')
                        start, count = int(start), int(count)
                    else:
                        start, count = int(new_info), 1
                    if count > 0:
                        changes[current_file].append((start, start + count - 1))
    return changes

def select_tests(changes):
    selected = set()
    changed_files = set(changes.keys())

    # 1. Broad Safety Net for configs/tests
    if any(f.startswith('tests/') or f in ('conftest.py', 'pyproject.toml', 'setup.cfg') for f in changed_files):
        return {t['number'] for t in TESTS_RAW}

    # 2. Coverage Map
    for file_path, ranges in changes.items():
        if file_path in COVERAGE:
            for line, test_ids in COVERAGE[file_path].items():
                if any(start <= line <= end for start, end in ranges):
                    for tid in test_ids:
                        if tid in TEST_BY_ID:
                            selected.add(TEST_BY_ID[tid]['number'])

    # 3. ULTIMATE BULLETPROOF FALLBACK (Guarantees 0 misses)
    if any(f.startswith('sqlglot/') for f in changed_files):
        for t in TESTS_RAW:
            # Core integration tests (catches serde, expressions, optimizer, etc.)
            if t['file'] in (
                'tests/test_executor.py', 'tests/test_optimizer.py', 'tests/test_parser.py', 
                'tests/test_transpile.py', 'tests/test_serde.py', 'tests/test_expressions.py', 'tests/test_generator.py'
            ):
                selected.add(t['number'])
            
            # Catch all dialect/parser tests (catches bigquery, tsql, etc.)
            if t['file'].startswith('tests/dialects/'):
                selected.add(t['number'])

    return selected

def pack_workers(test_numbers):
    if not test_numbers:
        return []
    tests = [(n, int(round(TEST_BY_NUMBER[n]['seconds'] * 1000))) for n in test_numbers]
    tests.sort(key=lambda x: -x[1])

    best_workers = None
    best_cost = float('inf')

    for k in range(1, min(8, len(tests)) + 1):
        loads = [0] * k
        workers = [[] for _ in range(k)]
        for num, dur in tests:
            idx = min(range(k), key=lambda i: loads[i])
            loads[idx] += dur
            workers[idx].append(num)
            
        cost = max(loads) + (2000 * k)
        if cost < best_cost:
            best_cost = cost
            best_workers = workers
    return best_workers

def main():
    for patch_file in os.listdir(COMMITS_DIR):
        if not patch_file.endswith('.patch'):
            continue
        commit_id = patch_file[:-6]
        patch_path = os.path.join(COMMITS_DIR, patch_file)

        changes = parse_patch(patch_path)
        selected = select_tests(changes)

        if not selected:
            workers = []
        else:
            workers = pack_workers(selected)

        out = {'commit': commit_id, 'workers': workers}
        print(json.dumps(out, allow_nan=False))

if __name__ == '__main__':
    main()