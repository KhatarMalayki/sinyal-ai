"""Generate real-model benchmark samples through an OpenAI-compatible API.

The API key is read only from SINYAL_AI_API_KEY and is never written to disk.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from benchmark_expanded import DATA, MAX_WORDS, OUT, PROMPTS, evaluate

BASE_URL = os.environ.get('SINYAL_AI_BASE_URL', 'http://localhost:20128/v1').rstrip('/')
DEFAULT_MODELS = [
    'kimchi/minimax-m3',
    'ollama/minimax-m3',
    'kimchi/kimi-k2.7',
    'gemini/gemini-3.5-flash',
    'gemini/gemini-3.1-flash-lite-preview',
    'gemini/gemini-3-flash-preview',
    'ag/gemini-3.5-flash-low',
    'ag/gemini-3.1-pro-low',
]
REQUESTED_MODELS = [model.strip() for model in
                    os.environ.get('SINYAL_AI_MODELS', ','.join(DEFAULT_MODELS)).split(',')
                    if model.strip()]
API_KEY = os.environ.get('SINYAL_AI_API_KEY')
REAL_DATA = OUT / 'dataset-real-ai-multimodel.csv'
CHECKPOINT = OUT / 'real-ai-multimodel-checkpoint.csv'
TIMEOUT = 90
MAX_ATTEMPTS = 4
MAX_HTTP_ATTEMPTS = 6


def api_request(path, payload=None):
    headers = {'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json',
               'Accept': 'application/json'}
    body = json.dumps(payload).encode('utf-8') if payload is not None else None
    for attempt in range(1, MAX_HTTP_ATTEMPTS + 1):
        request = Request(f'{BASE_URL}{path}', data=body, headers=headers,
                          method='POST' if body else 'GET')
        try:
            with urlopen(request, timeout=TIMEOUT) as response:
                raw = response.read().decode('utf-8', errors='replace').strip()
                if not raw:
                    raise RuntimeError(f'API returned an empty HTTP {response.status} response for {path}')
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    # Some OpenAI-compatible routers return SSE even when stream=false.
                    events = []
                    for line in raw.splitlines():
                        if not line.startswith('data:'):
                            continue
                        data = line[5:].strip()
                        if data and data != '[DONE]':
                            events.append(json.loads(data))
                    if not events:
                        content_type = response.headers.get('Content-Type', 'unknown')
                        preview = re.sub(r'\s+', ' ', raw)[:200]
                        raise RuntimeError(f'Non-JSON API response ({content_type}): {preview}')
                    content = ''.join(
                        event.get('choices', [{}])[0].get('delta', {}).get('content', '') or
                        event.get('choices', [{}])[0].get('message', {}).get('content', '')
                        for event in events if event.get('choices')
                    )
                    final = events[-1]
                    return {'id':final.get('id',''), 'model':final.get('model',''),
                            'choices':[{'message':{'content':content}}]}
        except HTTPError as error:
            detail = error.read().decode('utf-8', errors='replace')[:500]
            if error.code != 429 or attempt == MAX_HTTP_ATTEMPTS:
                raise RuntimeError(f'API HTTP {error.code}: {detail}') from error
            retry_after = error.headers.get('Retry-After', '')
            reset_match = re.search(r'reset after\s+(\d+)s', detail, re.IGNORECASE)
            delay = (int(retry_after) if retry_after.isdigit() else
                     int(reset_match.group(1)) if reset_match else min(2 ** attempt, 30))
            delay = max(1, delay + 1)
            print(f'  HTTP 429; retry {attempt}/{MAX_HTTP_ATTEMPTS} in {delay}s...', flush=True)
            time.sleep(delay)
        except URLError as error:
            raise RuntimeError(f'API connection failed: {error.reason}') from error


def clean(text):
    text = re.sub(r'\s+', ' ', text or '').strip()
    return ' '.join(text.split()[:MAX_WORDS])


def extract_text(response):
    choices = response.get('choices') or []
    choice = choices[0] if choices else {}
    message = choice.get('message') or {}
    candidates = [
        message.get('content'), message.get('reasoning_content'),
        choice.get('text'), response.get('output_text'), response.get('content'),
    ]
    output = response.get('output') or []
    for item in output if isinstance(output, list) else []:
        for part in item.get('content', []) if isinstance(item, dict) else []:
            if isinstance(part, dict):
                candidates.extend([part.get('text'), part.get('content')])
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return clean(candidate)
        if isinstance(candidate, list):
            joined = ' '.join(part.get('text','') for part in candidate if isinstance(part,dict))
            if joined.strip():
                return clean(joined)
    return ''


def response_shape(response):
    """Return field names/types only; never include generated text."""
    shape = {'root_keys':sorted(response.keys()) if isinstance(response,dict) else [],
             'root_type':type(response).__name__}
    choices = response.get('choices') if isinstance(response,dict) else None
    if isinstance(choices,list) and choices:
        choice = choices[0]
        shape['choice_keys'] = sorted(choice.keys()) if isinstance(choice,dict) else []
        message = choice.get('message') if isinstance(choice,dict) else None
        shape['message_keys'] = sorted(message.keys()) if isinstance(message,dict) else []
        shape['finish_reason'] = choice.get('finish_reason') if isinstance(choice,dict) else None
    return shape


def generate(human, index, requested_model):
    prompt_id = f"{human['genre']}-real-v1"
    prompt = PROMPTS[human['genre']].format(topic=human['topic'])
    prompt += (' Panjang 120–170 kata. Gunakan gaya alami dan spesifik. '
               'Jangan menyebut bahwa Anda AI. Keluarkan hanya teks utama.')
    payload = {
        'model': requested_model,
        'messages': [
            {'role':'system','content':'Anda menulis teks bahasa Indonesia yang alami.'},
            {'role':'user','content':prompt},
        ],
        'temperature': [0.25, 0.65, 0.95][index % 3],
        # Reasoning-capable routes may consume most of a small token budget
        # before emitting visible content. Keep enough room for 120–170 words.
        'max_tokens': 4096,
        'stream': False,
    }
    started = datetime.now(timezone.utc).isoformat()
    response, text = None, ''
    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = api_request('/chat/completions', payload)
        text = extract_text(response)
        if len(text.split()) >= 80:
            break
        print(f'  retry {attempt}/{MAX_ATTEMPTS}: response has {len(text.split())} words; '
              f'shape={json.dumps(response_shape(response))}', flush=True)
        time.sleep(attempt)
    if len(text.split()) < 80:
        raise RuntimeError(f'Response too short after {MAX_ATTEMPTS} attempts '
                           f'({len(text.split())} words) for {human["topic"]}')
    return {
        'id':'', 'label':'ai', 'topic':human['topic'], 'genre':human['genre'],
        'corpus':human['corpus'], 'text':text, 'source':f'{BASE_URL}/chat/completions',
        'revision':str(response.get('id','')), 'license':'Generated benchmark sample',
        'generator':'OpenAI-compatible local API',
        'requested_model':requested_model,
        'model':response.get('model') or requested_model,
        'prompt_id':prompt_id, 'generated_at':started, 'fallback':'false'
    }


def write_rows(path, rows):
    if not rows:
        return
    with path.open('w', newline='', encoding='utf-8-sig') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def build_schedule(humans):
    """Assign each model exactly one sample from each of the three genres."""
    if len(REQUESTED_MODELS) != 8 or len(set(REQUESTED_MODELS)) != 8:
        raise RuntimeError('SINYAL_AI_MODELS must contain exactly 8 unique model IDs.')
    by_genre = {}
    for human in humans:
        by_genre.setdefault(human['genre'], []).append(human)
    if set(by_genre) != set(PROMPTS):
        raise RuntimeError(f'Expected genres {sorted(PROMPTS)}, found {sorted(by_genre)}.')
    if any(len(rows) != len(REQUESTED_MODELS) for rows in by_genre.values()):
        counts = {genre:len(rows) for genre, rows in by_genre.items()}
        raise RuntimeError(f'Need exactly one topic per model in each genre; counts={counts}.')
    schedule = []
    for genre in PROMPTS:
        for model_index, human in enumerate(sorted(by_genre[genre], key=lambda row: row['topic'])):
            schedule.append((human, REQUESTED_MODELS[model_index]))
    return schedule


def validate_checkpoint(rows, schedule):
    if len(rows) > len(schedule):
        raise RuntimeError('Checkpoint has more rows than the current generation schedule.')
    for index, row in enumerate(rows):
        human, requested_model = schedule[index]
        identity = (row.get('topic'), row.get('genre'), row.get('requested_model'))
        expected = (human['topic'], human['genre'], requested_model)
        if identity != expected:
            raise RuntimeError('Checkpoint does not match the current model list/dataset at row '
                               f'{index + 1}: expected={expected}, found={identity}. '
                               'Move or delete the checkpoint before restarting.')


def validate_completed(humans, generated, schedule):
    validate_checkpoint(generated, schedule)
    if len(generated) != len(schedule) or len(humans) != 24:
        raise RuntimeError(f'Incomplete dataset: humans={len(humans)}, AI={len(generated)}.')
    requested_counts = {model:0 for model in REQUESTED_MODELS}
    genre_model_pairs = set()
    for row in generated:
        requested_counts[row['requested_model']] += 1
        genre_model_pairs.add((row['genre'], row['requested_model']))
        if row.get('fallback') != 'false' or len(row.get('text', '').split()) < 80:
            raise RuntimeError(f'Invalid generated row for {row.get("topic")}')
    if set(requested_counts.values()) != {3} or len(genre_model_pairs) != 24:
        raise RuntimeError(f'Unbalanced model assignment: {requested_counts}')


def main():
    if not API_KEY:
        raise SystemExit('ERROR: SINYAL_AI_API_KEY is not set in this terminal.')
    if not DATA.exists():
        raise SystemExit(f'ERROR: source human dataset not found: {DATA}')
    models = api_request('/models')
    available = {item.get('id') for item in models.get('data', []) if item.get('id')}
    if available:
        missing = [model for model in REQUESTED_MODELS if model not in available]
        if missing:
            gemini_models = sorted(model for model in available if 'gemini' in model.lower())
            raise RuntimeError(f'Requested model IDs not advertised by /models: {missing}. '
                               f'Advertised Gemini IDs: {gemini_models}')
    print(f'API connected. Requested models ({len(REQUESTED_MODELS)}): {REQUESTED_MODELS}')
    with DATA.open(newline='', encoding='utf-8-sig') as file:
        humans = [row for row in csv.DictReader(file) if row['label']=='human']
    schedule = build_schedule(humans)
    generated = []
    if CHECKPOINT.exists():
        with CHECKPOINT.open(newline='', encoding='utf-8-sig') as file:
            generated = list(csv.DictReader(file))
        validate_checkpoint(generated, schedule)
        print(f'Resuming from checkpoint: {len(generated)}/{len(schedule)} samples')
    for index, (human, requested_model) in enumerate(schedule):
        if index < len(generated):
            continue
        print(f'[{index+1:02}/{len(schedule)}] {human["genre"]}: {human["topic"]} '
              f'-> {requested_model}', flush=True)
        generated.append(generate(human, index, requested_model))
        write_rows(CHECKPOINT, generated)
        time.sleep(.15)
    validate_completed(humans, generated, schedule)
    # Add the requested-model column to human rows so the CSV schema is uniform.
    humans = [{**row, 'requested_model':''} for row in humans]
    rows = humans + generated
    for index, row in enumerate(rows, 1):
        row['id'] = f"{row['label']}-{index:03}"
    temporary = REAL_DATA.with_suffix('.tmp')
    write_rows(temporary, rows)
    temporary.replace(REAL_DATA)
    # Promote only after all validation and atomic output completion.
    DATA.write_bytes(REAL_DATA.read_bytes())
    report = evaluate(rows)
    CHECKPOINT.unlink(missing_ok=True)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f'Wrote {REAL_DATA} and refreshed expanded report/results.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'ERROR: {error}', file=sys.stderr)
        raise SystemExit(1)