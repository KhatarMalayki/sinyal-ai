"""One-shot outer-holdout gate for the frozen v2 stylometric candidate."""
from __future__ import annotations

import csv
import json
from collections import Counter

from benchmark import classification_metrics
from benchmark_expanded import OUT
from calibrate_features_v2 import MANIFEST, DATA, FROZEN, raw_score

RESULT = OUT / 'feature-v2-holdout.json'

# Locked before the one-shot read, with explicit user approval on 2026-07-20.
PROMOTION_GATES = {
    'mcc': .30,
    'balanced_accuracy': .70,
    'specificity': .65,
    'recall': .70,
    'minimum_genre_balanced_accuracy': .60,
}


def load_holdout_once():
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    entries = manifest.get('topics', manifest.get('assignments', []))
    assignments = ({entry['topic']:entry['split'] for entry in entries}
                   if isinstance(entries, list) else entries)
    topics = {topic for topic, split in assignments.items() if split == 'holdout'}
    if manifest.get('created_before_ai_generation') is not True or len(topics) != 25:
        raise RuntimeError('Invalid frozen outer-holdout manifest')
    rows = []
    with DATA.open(newline='', encoding='utf-8-sig') as file:
        for row in csv.DictReader(file):
            if row['topic'] in topics:
                rows.append(row)
    counts = Counter(row['topic'] for row in rows)
    if len(rows) != 50 or set(counts.values()) != {2}:
        raise RuntimeError('Expected 25 intact holdout pairs / 50 rows')
    return rows


def metrics(rows, threshold, config):
    scored = [{**row, 'score':100 if raw_score(row['text'], config) >= threshold else 0}
              for row in rows]
    return classification_metrics(scored, 50)


def main():
    if RESULT.exists():
        raise RuntimeError('Outer holdout already evaluated; refusing a second look')
    frozen = json.loads(FROZEN.read_text(encoding='utf-8'))
    if not frozen.get('calibration_pass') or frozen.get('outer_holdout_scored') is not False:
        raise RuntimeError('Candidate is not eligible for one-shot holdout evaluation')

    rows = load_holdout_once()
    overall = metrics(rows, frozen['threshold'], frozen['config'])
    by_genre = {genre:metrics([row for row in rows if row['genre'] == genre],
                              frozen['threshold'], frozen['config'])
                for genre in sorted({row['genre'] for row in rows})}
    minimum_genre_ba = min(metric['balanced_accuracy'] for metric in by_genre.values())
    checks = {
        'mcc':overall['mcc'] >= PROMOTION_GATES['mcc'],
        'balanced_accuracy':overall['balanced_accuracy'] >= PROMOTION_GATES['balanced_accuracy'],
        'specificity':overall['specificity'] >= PROMOTION_GATES['specificity'],
        'recall':overall['recall'] >= PROMOTION_GATES['recall'],
        'minimum_genre_balanced_accuracy':minimum_genre_ba >= PROMOTION_GATES['minimum_genre_balanced_accuracy'],
    }
    result = {'candidate':frozen['candidate'], 'threshold':frozen['threshold'],
              'holdout_topics':25, 'holdout_rows':50, 'promotion_gates':PROMOTION_GATES,
              'overall_metrics':overall, 'by_genre':by_genre,
              'minimum_genre_balanced_accuracy':minimum_genre_ba,
              'gate_checks':checks, 'promotion_pass':all(checks.values()),
              'one_shot':True, 'retuning_permitted':False}
    RESULT.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()