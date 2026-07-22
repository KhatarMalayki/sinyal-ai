"""Select on the frozen v2 calibration split, then open holdout exactly once."""
from __future__ import annotations

import argparse
import csv
import json

from benchmark import classification_metrics, score_text as production_score
from benchmark_expanded import OUT
from calibrate_formula import CANDIDATES, candidate_score

DATA = OUT / 'dataset-real-ai-multimodel-v2.csv'
MANIFEST = OUT / 'v2-split-manifest.json'
FROZEN = OUT / 'formula-v2-frozen.json'
CALIBRATION_REPORT = OUT / 'formula-v2-calibration.json'
HOLDOUT_REPORT = OUT / 'formula-v2-holdout.json'

# Declared before holdout evaluation. A candidate must satisfy every holdout
# gate and materially improve MCC over the unchanged production formula.
CALIBRATION_GATES = {'mcc': .20, 'balanced_accuracy': .60, 'specificity': .65}
HOLDOUT_GATES = {'mcc': .10, 'balanced_accuracy': .58, 'specificity': .60}
MIN_HOLDOUT_MCC_IMPROVEMENT = .15
OBJECTIVE_ORDER = ('mcc', 'balanced_accuracy', 'specificity', 'f1')


def manifest_map():
    payload = json.loads(MANIFEST.read_text(encoding='utf-8'))
    if payload.get('created_before_ai_generation') is not True:
        raise RuntimeError('v2 manifest is not marked as frozen before AI generation')
    entries = payload.get('topics', payload.get('assignments', []))
    result = ({entry['topic']:entry['split'] for entry in entries}
              if isinstance(entries, list) else entries)
    if len(result) != 96 or set(result.values()) != {'calibration', 'holdout'}:
        raise RuntimeError('Invalid v2 split manifest')
    return result


def load_split(split):
    assignments = manifest_map()
    rows = []
    with DATA.open(newline='', encoding='utf-8-sig') as file:
        for row in csv.DictReader(file):
            if assignments.get(row['topic']) == split:
                rows.append(row)
    expected = 142 if split == 'calibration' else 50
    if len(rows) != expected or any(sum(r['topic']==row['topic'] for r in rows) != 2 for row in rows):
        raise RuntimeError(f'Expected {expected} paired {split} rows, found {len(rows)}')
    return rows


def metric_key(metric):
    return tuple(metric[name] for name in OBJECTIVE_ORDER)


def best_threshold(rows):
    metrics = [classification_metrics(rows, threshold) for threshold in range(5, 96)]
    # Reject thresholds that miss the predeclared calibration specificity gate.
    eligible = [m for m in metrics if m['specificity'] >= CALIBRATION_GATES['specificity']]
    return max(eligible or metrics, key=metric_key)


def gates_pass(metric, gates):
    return all(metric[name] >= minimum for name, minimum in gates.items())


def select_and_freeze():
    if FROZEN.exists() or HOLDOUT_REPORT.exists():
        raise RuntimeError('v2 formula is already frozen/evaluated; refusing to retune')
    rows = load_split('calibration')
    candidates = {}
    for name, config in CANDIDATES.items():
        scored = [{**row, 'score':candidate_score(row['text'], config)} for row in rows]
        candidates[name] = best_threshold(scored)
    eligible = [name for name, metric in candidates.items()
                if gates_pass(metric, CALIBRATION_GATES)]
    winner = max(eligible or candidates, key=lambda name: metric_key(candidates[name]))
    calibration_pass = winner in eligible
    frozen = {
        'candidate':winner, 'config':CANDIDATES[winner],
        'threshold':candidates[winner]['threshold'],
        'manifest':MANIFEST.name, 'objective_order':list(OBJECTIVE_ORDER),
        'calibration_gates':CALIBRATION_GATES, 'holdout_gates':HOLDOUT_GATES,
        'min_holdout_mcc_improvement_vs_production':MIN_HOLDOUT_MCC_IMPROVEMENT,
        'calibration_pass':calibration_pass,
    }
    report = {'calibration_samples':len(rows), 'holdout_samples_not_scored':50,
              'candidates':candidates, 'winner':winner,
              'calibration_pass':calibration_pass}
    CALIBRATION_REPORT.write_text(json.dumps(report, indent=2), encoding='utf-8')
    FROZEN.write_text(json.dumps(frozen, indent=2), encoding='utf-8')
    print(json.dumps({'frozen':frozen, 'calibration_metrics':candidates[winner],
                      'holdout_scored':False}, indent=2))


def evaluate_frozen():
    if HOLDOUT_REPORT.exists():
        raise RuntimeError('v2 holdout was already evaluated; refusing a second look')
    frozen = json.loads(FROZEN.read_text(encoding='utf-8'))
    if not frozen.get('calibration_pass'):
        raise RuntimeError('Frozen candidate failed calibration gates; holdout remains unopened')
    rows = load_split('holdout')
    candidate_rows = [{**row, 'score':candidate_score(row['text'], frozen['config'])}
                      for row in rows]
    production_rows = [{**row, 'score':production_score(row['text'])} for row in rows]
    candidate = classification_metrics(candidate_rows, frozen['threshold'])
    production = classification_metrics(production_rows, frozen['threshold'])
    improvement = candidate['mcc'] - production['mcc']
    passed = (gates_pass(candidate, frozen['holdout_gates']) and
              improvement >= frozen['min_holdout_mcc_improvement_vs_production'])
    result = {'candidate':frozen['candidate'], 'threshold':frozen['threshold'],
              'holdout_samples':len(rows), 'metrics':candidate,
              'production_formula_same_threshold':production,
              'mcc_improvement_vs_production':improvement, 'promotion_pass':passed}
    HOLDOUT_REPORT.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--select', action='store_true')
    action.add_argument('--evaluate-frozen', action='store_true')
    args = parser.parse_args()
    select_and_freeze() if args.select else evaluate_frozen()