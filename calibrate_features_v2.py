"""Calibration-only search for a new non-topical stylometric feature family.

The outer v2 holdout is never scored here. Candidate comparison uses paired,
deterministic five-fold out-of-fold predictions on calibration topics only.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from statistics import mean, pvariance

from benchmark import classification_metrics
from benchmark_expanded import OUT

DATA = OUT / 'dataset-real-ai-multimodel-v2.csv'
MANIFEST = OUT / 'v2-split-manifest.json'
REPORT = OUT / 'feature-v2-calibration-cv.json'
FROZEN = OUT / 'feature-v2-frozen.json'
CV_SALT = 'sinyal-ai-v2-calibration-paired-cv-v1'
FOLDS = 5
OBJECTIVE = ('mcc', 'balanced_accuracy', 'specificity', 'f1')
GATES = {'mcc': .20, 'balanced_accuracy': .60, 'specificity': .65}

# Small, declared family. All signals are structural/stylometric; none uses
# topic nouns, source names, model IDs, genre, or document provenance.
CANDIDATES = {
    'rhythm_and_closure': {
        'sentence_uniformity': .26, 'paragraph_uniformity': .10,
        'sentence_closure': .18, 'comma_uniformity': .12,
        'function_stability': .15, 'lexical_stability': .09,
        'digit_density': -.05, 'quote_density': -.05,
    },
    'function_and_rhythm': {
        'sentence_uniformity': .24, 'paragraph_uniformity': .08,
        'sentence_closure': .12, 'comma_uniformity': .10,
        'function_stability': .25, 'lexical_stability': .15,
        'digit_density': -.03, 'quote_density': -.03,
    },
    'low_format_bias': {
        'sentence_uniformity': .30, 'paragraph_uniformity': .05,
        'sentence_closure': .16, 'comma_uniformity': .14,
        'function_stability': .20, 'lexical_stability': .15,
        'digit_density': 0, 'quote_density': 0,
    },
}


def clamp(value, low=0.0, high=1.0):
    return min(high, max(low, value))


def tokens(text):
    return re.findall(r"[a-zà-ÿ0-9]+(?:['’-][a-zà-ÿ]+)*", text.lower(), re.I)


def coefficient_uniformity(values, scale=1.0, fallback=.35):
    if len(values) < 2:
        return fallback
    avg = mean(values)
    return 1 - clamp(math.sqrt(pvariance(values)) / max(avg * scale, 1))


def window_rates(words, vocabulary, windows=4):
    if not words:
        return [0]
    size = max(1, math.ceil(len(words) / windows))
    chunks = [words[index:index+size] for index in range(0, len(words), size)]
    return [sum(word in vocabulary for word in chunk) / len(chunk) for chunk in chunks]


def features(text):
    ws = tokens(text)
    sentences = [part.strip() for part in re.split(r'(?<=[.!?])\s+', text) if part.strip()]
    if len(sentences) < 2:
        sentences = [part.strip() for part in re.split(r'[.!?]+', text) if part.strip()]
    paragraphs = [part.strip() for part in re.split(r'\n\s*\n', text) if part.strip()]
    sentence_lengths = [len(tokens(sentence)) for sentence in sentences if tokens(sentence)]
    paragraph_lengths = [len(tokens(paragraph)) for paragraph in paragraphs if tokens(paragraph)]
    comma_counts = [sentence.count(',') for sentence in sentences]
    closed = sum(sentence.rstrip().endswith(('.', '!', '?')) for sentence in sentences)
    closure_rate = closed / max(len(sentences), 1)

    function_words = {'yang','dan','di','ke','dari','untuk','dengan','pada','dalam',
                      'oleh','karena','agar','tetapi','juga','atau','sebagai','itu','ini'}
    rates = window_rates(ws, function_words)
    lexical_windows = []
    size = max(1, math.ceil(len(ws) / 4))
    for index in range(0, len(ws), size):
        chunk = ws[index:index+size]
        lexical_windows.append(len(set(chunk)) / max(len(chunk), 1))

    return {
        'sentence_uniformity': coefficient_uniformity(sentence_lengths, .72),
        'paragraph_uniformity': coefficient_uniformity(paragraph_lengths, .85),
        'sentence_closure': clamp((closure_rate - .45) / .55),
        'comma_uniformity': coefficient_uniformity(comma_counts, 1.15),
        'function_stability': coefficient_uniformity(rates, 2.1),
        'lexical_stability': coefficient_uniformity(lexical_windows, 2.0),
        'digit_density': clamp(sum(char.isdigit() for char in text) / max(len(text), 1) * 35),
        'quote_density': clamp(sum(char in '"“”‘’' for char in text) / max(len(text), 1) * 55),
    }


def raw_score(text, config):
    values = features(text)
    return sum(values[name] * weight for name, weight in config.items())


def calibration_topics():
    payload = json.loads(MANIFEST.read_text(encoding='utf-8'))
    if payload.get('created_before_ai_generation') is not True:
        raise RuntimeError('Manifest is not frozen before AI generation')
    entries = payload.get('topics', payload.get('assignments', []))
    assignments = ({entry['topic']:entry['split'] for entry in entries}
                   if isinstance(entries, list) else entries)
    topics = {topic for topic, split in assignments.items() if split == 'calibration'}
    if len(topics) != 71:
        raise RuntimeError(f'Expected 71 calibration topics, found {len(topics)}')
    return topics


def load_calibration():
    allowed = calibration_topics()
    rows = []
    with DATA.open(newline='', encoding='utf-8-sig') as file:
        for row in csv.DictReader(file):
            # Do not derive features or retain content for outer-holdout topics.
            if row['topic'] in allowed:
                rows.append(row)
    counts = Counter(row['topic'] for row in rows)
    if len(rows) != 142 or set(counts.values()) != {2}:
        raise RuntimeError('Calibration rows are not 71 intact human/AI pairs')
    if Counter(row['label'] for row in rows) != {'human':71, 'ai':71}:
        raise RuntimeError('Calibration labels are not balanced')
    return rows


def canonical_topic(topic):
    return unicodedata.normalize('NFKC', topic).strip().casefold()


def fold_map(rows):
    topics = sorted({row['topic'] for row in rows}, key=lambda topic: (
        hashlib.sha256(f'{CV_SALT}:{canonical_topic(topic)}'.encode()).digest(),
        canonical_topic(topic)))
    result = {topic:index % FOLDS for index, topic in enumerate(topics)}
    sizes = Counter(result.values())
    if max(sizes.values()) - min(sizes.values()) > 1:
        raise RuntimeError(f'Unbalanced CV topic folds: {sizes}')
    return result


def scored(rows, config):
    return [{**row, 'raw':raw_score(row['text'], config)} for row in rows]


def threshold_metrics(rows, threshold):
    prepared = [{**row, 'score':100 if row['raw'] >= threshold else 0} for row in rows]
    return classification_metrics(prepared, 50)


def best_threshold(rows):
    values = sorted({row['raw'] for row in rows})
    thresholds = [values[0] - 1e-9] + [(a+b)/2 for a,b in zip(values, values[1:])] + [values[-1]+1e-9]
    metrics = [(threshold_metrics(rows, threshold), threshold) for threshold in thresholds]
    eligible = [item for item in metrics if item[0]['specificity'] >= GATES['specificity']]
    metric, threshold = max(eligible or metrics,
                            key=lambda item: tuple(item[0][name] for name in OBJECTIVE))
    return threshold, metric


def cross_validate(rows, config, folds):
    predictions, fold_reports = [], []
    for fold in range(FOLDS):
        train = [row for row in rows if folds[row['topic']] != fold]
        validation = [row for row in rows if folds[row['topic']] == fold]
        threshold, train_metric = best_threshold(train)
        predictions.extend({**row, 'score':100 if row['raw'] >= threshold else 0}
                           for row in validation)
        fold_reports.append({'fold':fold, 'train_rows':len(train),
                             'validation_rows':len(validation), 'threshold':threshold,
                             'train_metrics':train_metric})
    return classification_metrics(predictions, 50), fold_reports


def passes(metric):
    return all(metric[name] >= minimum for name, minimum in GATES.items())


def main():
    if FROZEN.exists():
        raise RuntimeError('A new-feature v2 candidate is already frozen; refusing to retune')
    rows = load_calibration()
    folds = fold_map(rows)
    results = {}
    for name, config in CANDIDATES.items():
        candidate_rows = scored(rows, config)
        oof, fold_reports = cross_validate(candidate_rows, config, folds)
        full_threshold, full_metric = best_threshold(candidate_rows)
        results[name] = {'oof_metrics':oof, 'folds':fold_reports,
                         'full_calibration_threshold':full_threshold,
                         'full_calibration_metrics':full_metric,
                         'passes_oof_gates':passes(oof)}
    eligible = [name for name, result in results.items() if result['passes_oof_gates']]
    winner = max(eligible or results, key=lambda name: tuple(
        results[name]['oof_metrics'][metric] for metric in OBJECTIVE))
    frozen = {'candidate':winner, 'config':CANDIDATES[winner],
              'threshold':results[winner]['full_calibration_threshold'],
              'oof_metrics':results[winner]['oof_metrics'],
              'calibration_pass':winner in eligible, 'gates':GATES,
              'objective_order':list(OBJECTIVE), 'cv_folds':FOLDS,
              'cv_salt':CV_SALT, 'outer_holdout_scored':False}
    REPORT.write_text(json.dumps({'calibration_rows':142, 'calibration_topics':71,
                                  'results':results, 'winner':winner}, indent=2), encoding='utf-8')
    FROZEN.write_text(json.dumps(frozen, indent=2), encoding='utf-8')
    print(json.dumps(frozen, indent=2))


if __name__ == '__main__':
    main()