"""Build and score a frozen 12-pair external detector comparison corpus."""
from __future__ import annotations

import argparse, csv, hashlib, json, time, unicodedata
from collections import Counter
from datetime import datetime, timezone

import generate_real_ai as api
from benchmark import classification_metrics, score_text
from benchmark_expanded import CORPORA, OUT
from build_v2_dataset import collect_corpus

HUMANS = OUT / 'external-comparison-human.csv'
MANIFEST = OUT / 'external-comparison-manifest.json'
DATA = OUT / 'external-comparison-dataset.csv'
CHECKPOINT = OUT / 'external-comparison-checkpoint.csv'
RESULTS = OUT / 'external-comparison-results.csv'
REPORT = OUT / 'external-comparison-report.json'
PER_GENRE = 4
MODELS = api.REQUESTED_MODELS[:4]


def canonical(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def read(path):
    with path.open(newline='', encoding='utf-8-sig') as file:
        return list(csv.DictReader(file))


def write(path, rows):
    api.write_rows(path, rows)


def exclusions():
    topics = set()
    for path in OUT.glob('*.csv'):
        if path in {HUMANS, DATA, RESULTS}:
            continue
        try:
            topics.update(canonical(row['topic']) for row in read(path) if row.get('topic'))
        except (KeyError, UnicodeDecodeError):
            pass
    return topics


def collect():
    if HUMANS.exists() or MANIFEST.exists():
        raise RuntimeError('External human corpus/manifest exists; refusing overwrite')
    excluded, rows = exclusions(), []
    for corpus in CORPORA:
        found = collect_corpus(*corpus, excluded | {canonical(r['topic']) for r in rows})
        rows.extend(found[:PER_GENRE])
    rows.sort(key=lambda row: (row['genre'], canonical(row['topic'])))
    for index, row in enumerate(rows, 1):
        row['id'] = f'external-human-{index:02}'
    if len(rows) != 12 or Counter(r['genre'] for r in rows) != Counter({g:4 for _,g,_,_ in CORPORA}):
        raise RuntimeError('External corpus must contain four humans per genre')
    if exclusions() & {canonical(r['topic']) for r in rows}:
        raise RuntimeError('External topics overlap existing datasets')
    write(HUMANS, rows)
    payload = {
        'version': 1, 'created_before_ai_generation': True,
        'purpose': 'exploratory external detector comparison; no tuning permitted',
        'pairs': 12, 'genres': 3, 'models': MODELS,
        'decision_rule': 'AI when score/probability >= 50; categorical AI=100, human=0',
        'metrics': ['mcc','balanced_accuracy','specificity','recall','coverage'],
        'human_sha256': hashlib.sha256(HUMANS.read_bytes()).hexdigest(),
        'created_at': datetime.now(timezone.utc).isoformat(),
    }
    MANIFEST.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'human_rows':len(rows), 'manifest':str(MANIFEST)}, indent=2))


def generate():
    if DATA.exists():
        raise RuntimeError('External dataset exists; refusing regeneration')
    humans, frozen = read(HUMANS), json.loads(MANIFEST.read_text(encoding='utf-8'))
    if hashlib.sha256(HUMANS.read_bytes()).hexdigest() != frozen['human_sha256']:
        raise RuntimeError('Frozen human corpus hash mismatch')
    generated = read(CHECKPOINT) if CHECKPOINT.exists() else []
    for index, row in enumerate(generated):
        if (row['topic'], row['requested_model']) != (humans[index]['topic'], MODELS[index % len(MODELS)]):
            raise RuntimeError(f'External checkpoint mismatch at row {index+1}')
    for index, human in enumerate(humans):
        if index < len(generated):
            continue
        model = MODELS[index % len(MODELS)]
        print(f'[{index+1:02}/12] {human["topic"]} -> {model}', flush=True)
        row = api.generate(human, index, model)
        row['id'], row['prompt_id'] = f'external-ai-{index+1:02}', f"{human['genre']}-external-v1"
        generated.append(row); write(CHECKPOINT, generated); time.sleep(.15)
    if any(len(r['text'].split()) < 80 or r['fallback'] != 'false' for r in generated):
        raise RuntimeError('Invalid generated external sample')
    write(DATA, humans + generated)
    CHECKPOINT.unlink(missing_ok=True)
    print(json.dumps({'rows':24, 'human':12, 'ai':12, 'output':str(DATA)}, indent=2))


def score_local():
    rows = read(DATA)
    scored = [{**row, 'tool':'sinyal-ai', 'tool_score':score_text(row['text']),
               'covered':'true'} for row in rows]
    write(RESULTS, scored)
    metric = classification_metrics([{**r,'score':int(r['tool_score'])} for r in scored], 50)
    REPORT.write_text(json.dumps({'sinyal-ai':{**metric,'coverage':1.0}}, indent=2), encoding='utf-8')
    print(json.dumps(metric, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('action', choices=['collect','generate','score-local'])
    action = parser.parse_args().action
    {'collect':collect, 'generate':generate, 'score-local':score_local}[action]()