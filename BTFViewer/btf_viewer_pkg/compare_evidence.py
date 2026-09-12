"""Raw focused comparison evidence shared by Qt and report renderers."""
COMPARE_EVIDENCE = [
    ('task_presence', 'New / Missing Tasks', 'summary', ['Task', 'Present in A', 'Present in B', 'CPU A', 'CPU B', 'Runs A', 'Runs B', 'Notes']),
    ('relative_changes', 'Largest Relative Changes', 'summary', ['Metric / Task', 'Baseline A', 'Candidate B', 'Absolute Δ', 'Relative Δ %', 'Direction']),
    ('core_distribution', 'Core Distribution Change', 'migrations', ['Task', 'Cores A', 'Cores B', 'Primary A', 'Primary B', 'Distribution Δ']),
    ('migration_concentration', 'Migration Concentration', 'migrations', ['Task', 'Migr A', 'Migr B', 'Share A %', 'Share B %', 'Share Δ']),
    ('timing_change_candidates', 'Timing Change Candidates', 'response', ['Task', 'Execution Max Δ', 'Blocking Max Δ', 'Response P99 Δ', 'Migration Δ', 'Reason to inspect']),
    ('trace_comparability', 'Trace Quality / Comparability', 'summary', ['Item', 'Baseline A', 'Candidate B', 'Difference', 'Compare Risk']),
]


def describe_core_distribution(a, b):
    ca, cb = set(a['cores']), set(b['cores'])
    if ca == cb:
        return 'Stable' if a['primary'] == b['primary'] else 'Primary changed'
    if ca <= cb:
        return 'Expanded'
    if cb <= ca:
        return 'Reduced'
    return 'Core set changed'


def build_comparison_evidence(a, b, metadata):
    out = {key: [] for key, *_ in COMPARE_EVIDENCE}
    empty = dict(cpu=0, runs=0, cores=[], primary=None, migrations=0, execution=0, blocking=0, response=0)
    ta, tb = sum(r['migrations'] for r in a.values()), sum(r['migrations'] for r in b.values())
    for name in sorted(a.keys() | b.keys()):
        x, y = a.get(name, empty), b.get(name, empty)
        if name not in a or name not in b:
            out['task_presence'].append([name, name in a, name in b, x['cpu'], y['cpu'], x['runs'], y['runs'], 'Missing in Candidate' if name in a else 'New in Candidate'])
        out['core_distribution'].append([name, x['cores'], y['cores'], x['primary'], y['primary'], describe_core_distribution(x, y)])
        sa, sb = (x['migrations'] / ta * 100 if ta else 0), (y['migrations'] / tb * 100 if tb else 0)
        if x['migrations'] or y['migrations']:
            out['migration_concentration'].append([name, x['migrations'], y['migrations'], sa, sb, sb - sa])
        reasons, deltas = [], []
        for key, label in [('execution', 'Execution Max'), ('blocking', 'Blocking Max'), ('response', 'Response P99'), ('migrations', 'Migrations')]:
            av, bv = x[key], y[key]
            d = bv - av
            deltas.append(-d if key == 'migrations' else d)
            if d:
                reason = ('Execution max ' + ('increased' if d > 0 else 'decreased') if key == 'execution' else 'Migration activity changed' if key == 'migrations' else label + ' changed')
                reasons.append(reason)
                out['relative_changes'].append([f'{label} / {name}', av, bv, d, d / av * 100 if av else None, 'Increased' if d > 0 else 'Decreased'])
        if reasons:
            out['timing_change_candidates'].append([name, *deltas, 'Multiple timing metrics changed' if len(reasons) > 1 else reasons[0]])
    out['relative_changes'].sort(key=lambda r: (-abs(r[4] if r[4] is not None else float('inf')), r[0]))
    out['migration_concentration'].sort(key=lambda r: (-max(r[3:5]), r[0]))
    out['timing_change_candidates'].sort(key=lambda r: (-max(map(abs, r[1:4])), -abs(r[4]), r[0]))
    out['trace_comparability'] = [[item, av, bv, 'Same' if av == bv else 'Different', 'No structural difference' if av == bv else 'Review difference; workload equivalence unknown'] for item, av, bv in metadata]
    return out


def format_evidence_cell(key, value, column):
    if value is None:
        return 'new' if key == 'relative_changes' and column == 4 else '—'
    if isinstance(value, list):
        return ', '.join(value) or '—'
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, (int, float)):
        percent = (key == 'task_presence' and column in (3, 4)) or (key == 'relative_changes' and column == 4) or (key == 'migration_concentration' and column >= 3)
        return f'{value:.1f}' if percent else f'{value:g}'
    return str(value)
