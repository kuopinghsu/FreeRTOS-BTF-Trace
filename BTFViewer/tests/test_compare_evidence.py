"""Focused evidence and Python/JavaScript contract regression coverage."""
import json
from pathlib import Path
import subprocess
from btf_viewer_pkg.compare_evidence import build_comparison_evidence


def test_cross_runtime_evidence_parity():
    base = dict(cpu=0, runs=0, cores=['Core_0'], primary='Core_0', migrations=0, execution=0, blocking=0, response=0)
    a = {'same': dict(base, migrations=2, execution=10), 'missing': dict(base, migrations=6)}
    b = {'same': dict(base, migrations=4, execution=20), 'added': dict(base, response=100)}
    metadata = [['Task count', 2, 2]]
    expected = build_comparison_evidence(a, b, metadata)
    web = Path(__file__).resolve().parents[1] / 'web'
    script = "import { buildComparisonEvidence } from './src/utils/compareEvidence.js'; console.log(JSON.stringify(buildComparisonEvidence(...JSON.parse(process.argv[1]))))"
    actual = json.loads(subprocess.check_output(['node', '--input-type=module', '-e', script, json.dumps([a, b, metadata])], cwd=web, text=True))
    assert actual == expected
    assert next(r for r in expected['migration_concentration'] if r[0] == 'same')[3:] == [25, 100, 75]
    assert next(r for r in expected['timing_change_candidates'] if r[0] == 'same')[4] == -2


def test_parsed_trace_pair_evidence_parity(tmp_path):
    from btf_viewer_pkg._bootstrap import install
    install()
    from btf_viewer_pkg.parser import _parse_btf, _build_trace_compare_rows
    paths = []
    for name, core, end in [('a', 'Core_0', 100), ('b', 'Core_1', 150)]:
        path = tmp_path / (name + '.btf')
        path.write_text(f'#version 2.2.0\n#timeScale ns\n0,{core},0,T,Worker,1,resume,\n{end},{core},0,T,Worker,1,preempt,\n200,{core},0,T,{name},2,resume,\n300,{core},0,T,{name},2,preempt,\n')
        paths.append(str(path))
    expected = _build_trace_compare_rows(*map(_parse_btf, paths), row_limit=None, top_limit=None)['evidence']
    script = """import fs from 'node:fs';
import { parseBtf } from './src/parser/btfParser.js';
import { buildAllCompareTables } from './src/utils/traceCompare.js';
const traces = await Promise.all(JSON.parse(process.argv[1]).map(p => parseBtf(fs.readFileSync(p, 'utf8'))));
console.log(JSON.stringify(buildAllCompareTables(...traces, null, null, false, null, 0).evidence));"""
    web = Path(__file__).resolve().parents[1] / 'web'
    actual = json.loads(subprocess.check_output(['node', '--input-type=module', '-e', script, json.dumps(paths)], cwd=web, text=True))
    for key in expected:
        if key == '_charts':
            for chart, rows in expected[key].items():
                web_key = {'core_util': 'coreUtil', 'inter_arrival': 'interArrival'}.get(chart, chart)
                assert sorted(actual[key][web_key], key=lambda r: r['label']) == sorted(rows, key=lambda r: r['label']), chart
        else:
            assert actual[key] == expected[key], key


def test_report_overview_and_summary_have_distinct_roles():
    from tests.test_trace_compare import _mini_trace
    from btf_viewer_pkg.parser import _build_trace_compare_rows, _build_compare_html
    a = _mini_trace({'Worker[1]': [(0, 100, 'Core_0')]})
    b = _mini_trace({'Worker[1]': [(0, 200, 'Core_0')]})
    html = _build_compare_html('Baseline', 'Candidate', False, _build_trace_compare_rows(a, b))
    overview = html.split('<h2>Overview</h2>')[1].split('<h2>Trace Quality / Comparability</h2>')[0]
    summary = html.split('<h2>Summary</h2>')[1].split('<h2>Overview</h2>')[0]
    assert 'Comparison identity' in overview
    assert 'compare-verdict-banner' not in overview
    assert 'Notable Changes' not in overview
    assert 'Notable Changes' in summary
    assert 'All summary metrics' in summary
    assert 'compare-decision-identity' not in summary
    assert 'compare-comparability-warn' not in summary
    assert html.count('class="compare-verdict-banner tone-') == 1
    assert html.count('class="compare-next"') <= 1
    assert html.index('<h2>Summary</h2>') < html.index('<h2>Largest Relative Changes</h2>')

    assert html.index('<h2>Summary</h2>') < html.index('<h2>Overview</h2>')
    assert summary.index('class="compare-cards"') < summary.index('class="compare-verdict-banner')
