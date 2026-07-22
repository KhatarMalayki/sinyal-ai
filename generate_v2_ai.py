"""Generate 96 balanced AI counterparts for the frozen v2 human corpus."""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path

import generate_real_ai as api
from benchmark_expanded import OUT
from build_v2_dataset import V2_HUMANS, V2_MANIFEST, validate as validate_humans

V2_DATA = OUT / 'dataset-real-ai-multimodel-v2.csv'
V2_CHECKPOINT = OUT / 'real-ai-multimodel-v2-checkpoint.csv'


def read_csv(path):
    with path.open(newline='', encoding='utf-8-sig') as file:
        return list(csv.DictReader(file))


def schedule(humans):
    """Round-robin each genre: 32 topics = 4 samples/model/genre."""
    rows = []
    for genre in api.PROMPTS:
        genre_rows = sorted((row for row in humans if row['genre']==genre),
                            key=lambda row: row['topic'])
        if len(genre_rows) != 32:
            raise RuntimeError(f'{genre}: expected 32 humans, found {len(genre_rows)}')
        rows.extend((human, api.REQUESTED_MODELS[index % 8])
                    for index, human in enumerate(genre_rows))
    return rows


def validate_checkpoint(rows, expected):
    if len(rows) > len(expected):
        raise RuntimeError('v2 checkpoint is longer than its schedule')
    for index, row in enumerate(rows):
        human, model = expected[index]
        found = (row.get('topic'), row.get('genre'), row.get('requested_model'))
        wanted = (human['topic'], human['genre'], model)
        if found != wanted:
            raise RuntimeError(f'v2 checkpoint mismatch at row {index+1}: {found} != {wanted}')


def validate_complete(humans, generated, expected):
    validate_humans(humans)
    validate_checkpoint(generated, expected)
    if len(generated) != 96:
        raise RuntimeError(f'Expected 96 generated rows, found {len(generated)}')
    counts = {model:sum(row['requested_model']==model for row in generated)
              for model in api.REQUESTED_MODELS}
    genre_pairs = {(row['genre'],row['requested_model']) for row in generated}
    if set(counts.values()) != {12} or len(genre_pairs) != 24:
        raise RuntimeError(f'Unbalanced v2 generation: {counts}')
    if len({row['text'] for row in generated}) != 96:
        raise RuntimeError('Duplicate AI texts found in v2')
    if any(row['fallback']!='false' or len(row['text'].split())<80 for row in generated):
        raise RuntimeError('v2 contains fallback or short AI samples')


def main():
    if not api.API_KEY:
        raise SystemExit('ERROR: SINYAL_AI_API_KEY is not set in this terminal.')
    if not V2_HUMANS.exists() or not V2_MANIFEST.exists():
        raise SystemExit('ERROR: run python build_v2_dataset.py first.')
    available_payload = api.api_request('/models')
    available = {item.get('id') for item in available_payload.get('data',[]) if item.get('id')}
    missing = [model for model in api.REQUESTED_MODELS if available and model not in available]
    if missing:
        raise RuntimeError(f'v2 requested model IDs unavailable: {missing}')
    humans = read_csv(V2_HUMANS)
    expected = schedule(humans)
    generated = read_csv(V2_CHECKPOINT) if V2_CHECKPOINT.exists() else []
    validate_checkpoint(generated, expected)
    print(f'v2 models valid; resuming {len(generated)}/96')
    for index, (human, model) in enumerate(expected):
        if index < len(generated):
            continue
        print(f'[{index+1:03}/096] {human["genre"]}: {human["topic"]} -> {model}', flush=True)
        row = api.generate(human, index, model)
        row['prompt_id'] = f"{human['genre']}-real-v2"
        generated.append(row)
        api.write_rows(V2_CHECKPOINT, generated)
        time.sleep(.15)
    validate_complete(humans, generated, expected)
    humans = [{**row, 'requested_model':''} for row in humans]
    rows = humans + generated
    for index, row in enumerate(rows, 1):
        row['id'] = f"{row['label']}-v2-{index:03}"
    temporary = V2_DATA.with_suffix('.tmp')
    api.write_rows(temporary, rows)
    temporary.replace(V2_DATA)
    V2_CHECKPOINT.unlink(missing_ok=True)
    actual = {}
    for row in generated:
        actual[row['model']] = actual.get(row['model'], 0) + 1
    print(json.dumps({'rows':len(rows),'human':96,'ai':96,
                      'requested_per_route':12,'actual_models':actual,
                      'fallbacks':0,'output':str(V2_DATA)}, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'ERROR: {error}')
        raise SystemExit(1)