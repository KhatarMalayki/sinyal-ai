"""Calibration-only formula selection with an explicit one-shot holdout gate.

`--select` scores calibration topics only and freezes one named candidate.
`--evaluate-frozen` reads that frozen choice and evaluates the untouched split.
The small candidate family is declared in source before either operation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path
from statistics import mean, pvariance

from benchmark import classification_metrics
from benchmark_expanded import OUT

DATA = OUT / 'dataset-real-ai-multimodel.csv'
FROZEN = OUT / 'formula-frozen.json'
CALIBRATION_REPORT = OUT / 'formula-calibration.json'
HOLDOUT_REPORT = OUT / 'formula-holdout.json'
SPLIT_SALT = 'sinyal-ai-multimodel-v1-unseen-holdout'

# Deliberately small, predeclared candidate family. In every candidate,
# lexical style is supporting evidence and never an independent max path.
CANDIDATES = {
    'balanced_no_expository_max': {
        'variation': .24, 'repetition': .25, 'vocabulary': .06, 'structure': .14,
        'style': .07, 'function': .08, 'clause': .10, 'personal': -.12,
        'repetition_floor': .70, 'center': .39, 'slope': 9.0,
    },
    'low_lexical_style': {
        'variation': .27, 'repetition': .27, 'vocabulary': .04, 'structure': .13,
        'style': .03, 'function': .09, 'clause': .11, 'personal': -.10,
        'repetition_floor': .68, 'center': .38, 'slope': 9.0,
    },
    'no_repetition_floor': {
        'variation': .28, 'repetition': .28, 'vocabulary': .04, 'structure': .14,
        'style': .04, 'function': .09, 'clause': .11, 'personal': -.10,
        'repetition_floor': 0, 'center': .36, 'slope': 9.0,
    },
}


def clamp(value, low=0, high=1):
    return min(high, max(low, value))


def words(text):
    return re.findall(r"[a-zà-ÿ0-9]+(?:['’-][a-zà-ÿ]+)*", text.lower(), re.I)


def variance(values):
    return pvariance(values) if values else 0


def features(text):
    ws = words(text)
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    lengths = [len(words(s)) for s in sentences if words(s)]
    avg_sentence = mean(lengths) if lengths else 0
    burstiness = math.sqrt(variance(lengths)) / max(avg_sentence, 1)
    bigrams = list(zip(ws, ws[1:]))
    counts = {}
    for item in bigrams:
        counts[item] = counts.get(item, 0) + 1
    repeated = sum(count - 1 for count in counts.values() if count > 1)
    repetition_ratio = repeated / max(len(bigrams), 1)
    lower = text.lower()
    connectors = ['selain itu','oleh karena itu','namun demikian','dengan demikian',
                  'pada akhirnya','secara keseluruhan','penting untuk',
                  'dapat disimpulkan','tidak hanya','di sisi lain']
    connector_rate = sum(lower.count(item) for item in connectors) / max(len(sentences), 1)
    starts = [' '.join(words(s)[:2]) for s in sentences if words(s)]
    start_variety = len(set(starts)) / max(len(starts), 1)
    punctuation_types = sum(mark in text for mark in [';',':','—','(',')','…'])
    paragraph_lengths = [len(words(p)) for p in paragraphs]
    uniformity = (1 - clamp(math.sqrt(variance(paragraph_lengths)) /
                  max(mean(paragraph_lengths), 1))) if len(paragraphs) > 1 else .5

    def hits(patterns):
        return sum(len(re.findall(pattern, lower)) for pattern in patterns)

    # Removed topical nouns (system, technology, information, data, etc.).
    style_hits = hits([
        r'\b(dapat|mampu|memungkinkan|membantu|memastikan)\b',
        r'\b(karena itu|sementara itu|misalnya|oleh sebab itu)\b',
    ])
    personal_hits = hits([
        r'\b(saya|aku|kami|kita|ku)\b',
        r'\b(kemarin|tadi|besok|pagi|siang|malam|minggu lalu)\b',
        r'\b(pergi|datang|duduk|berjalan|membeli|menelepon|melihat|menunggu)\b',
    ])
    function_words = {'yang','dan','di','ke','dari','untuk','dengan','pada','dalam',
                      'oleh','karena','agar','tetapi','juga','atau'}
    function_rate = sum(word in function_words for word in ws) / max(len(ws), 1)
    commas = [sentence.count(',') for sentence in sentences]
    return {
        'variation': clamp((.52 - burstiness) / .36),
        'repetition': clamp(repetition_ratio * 9 + (1 - start_variety) * .35),
        'vocabulary': clamp((.58 - len(set(ws))/max(len(ws), 1)) / .27),
        'structure': clamp(uniformity*.45 + connector_rate*.45 + (.16 if punctuation_types < 2 else 0)),
        'style': clamp(style_hits / max(len(sentences)*1.8, 1)),
        'function': clamp((function_rate - .105) / .09),
        'clause': 1-clamp(math.sqrt(variance(commas))/1.35) if len(sentences)>2 else .4,
        'personal': clamp(personal_hits / max(len(sentences)*1.15, 1)),
        'evidence': clamp((len(ws)-10)/120, .18, 1),
    }


def candidate_score(text, config):
    f = features(text)
    raw = sum(f[name] * config[name] for name in
              ('variation','repetition','vocabulary','structure','style','function','clause','personal'))
    if config['repetition_floor']:
        raw = max(raw, f['repetition'] * config['repetition_floor'])
    score = 100 / (1 + math.exp(-config['slope'] * (raw-config['center'])))
    score = 50 + (score-50) * f['evidence']
    return round(clamp(score, 4, 96))


def split_name(topic):
    digest = hashlib.sha256(f'{SPLIT_SALT}:{topic}'.encode()).digest()
    return 'holdout' if int.from_bytes(digest[:4], 'big') % 3 == 0 else 'calibration'


def load_rows():
    with DATA.open(newline='', encoding='utf-8-sig') as file:
        rows = list(csv.DictReader(file))
    if len(rows) != 48 or len({row['topic'] for row in rows}) != 24:
        raise RuntimeError('Expected the frozen 48-row, 24-topic multi-model dataset.')
    return rows


def best_threshold(rows):
    best = None
    for threshold in range(5, 96):
        metric = classification_metrics(rows, threshold)
        key = (metric['mcc'], metric['balanced_accuracy'], metric['specificity'], metric['f1'])
        if best is None or key > best[0]:
            best = (key, metric)
    return best[1]


def select_and_freeze():
    if FROZEN.exists() or HOLDOUT_REPORT.exists():
        raise RuntimeError('A formula is already frozen/evaluated; refusing to retune this holdout.')
    rows = [row for row in load_rows() if split_name(row['topic']) == 'calibration']
    candidates = {}
    for name, config in CANDIDATES.items():
        scored = [{**row, 'score':candidate_score(row['text'], config)} for row in rows]
        candidates[name] = best_threshold(scored)
    winner = max(candidates, key=lambda name: (
        candidates[name]['mcc'], candidates[name]['balanced_accuracy'],
        candidates[name]['specificity'], candidates[name]['f1']))
    frozen = {'candidate':winner, 'config':CANDIDATES[winner],
              'threshold':candidates[winner]['threshold'], 'split_salt':SPLIT_SALT}
    CALIBRATION_REPORT.write_text(json.dumps({
        'calibration_samples':len(rows), 'holdout_samples_not_scored':48-len(rows),
        'objective_order':['mcc','balanced_accuracy','specificity','f1'],
        'candidates':candidates, 'winner':winner,
    }, indent=2), encoding='utf-8')
    FROZEN.write_text(json.dumps(frozen, indent=2), encoding='utf-8')
    print(json.dumps({'frozen':frozen, 'calibration_metrics':candidates[winner],
                      'holdout_scored':False}, indent=2))


def evaluate_frozen():
    if HOLDOUT_REPORT.exists():
        raise RuntimeError('Holdout was already evaluated; refusing a second look.')
    frozen = json.loads(FROZEN.read_text(encoding='utf-8'))
    rows = [row for row in load_rows() if split_name(row['topic']) == 'holdout']
    scored = [{**row, 'score':candidate_score(row['text'], frozen['config'])} for row in rows]
    result = {'candidate':frozen['candidate'], 'threshold':frozen['threshold'],
              'holdout_samples':len(scored),
              'metrics':classification_metrics(scored, frozen['threshold'])}
    HOLDOUT_REPORT.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--select', action='store_true')
    action.add_argument('--evaluate-frozen', action='store_true')
    args = parser.parse_args()
    select_and_freeze() if args.select else evaluate_frozen()