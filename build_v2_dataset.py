"""Collect and freeze 96 new human topics plus a paired split manifest for v2."""
from __future__ import annotations

import csv
import hashlib
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError

from benchmark_expanded import CORPORA, OUT, clean_text
from urllib.parse import urlencode
from urllib.request import Request, urlopen

V1_DATA = OUT / 'dataset-real-ai-multimodel.csv'
V2_HUMANS = OUT / 'v2-human.csv'
V2_MANIFEST = OUT / 'v2-split-manifest.json'
PER_GENRE = 32
SPLIT_SALT = 'sinyal-ai-v2-20260719-frozen-before-generation'


def old_topics():
    if not V1_DATA.exists():
        return set()
    with V1_DATA.open(newline='', encoding='utf-8-sig') as file:
        return {row['topic'].casefold() for row in csv.DictReader(file)}


def collect_corpus(name, genre, api, license_name, excluded):
    rows, seen = [], set(excluded)
    for _ in range(80):
        params = {'action':'query','generator':'random','grnnamespace':0,'grnlimit':50,
                  'prop':'extracts|info','inprop':'url','explaintext':1,'exintro':1,
                  'format':'json','formatversion':2}
        request = Request(api+'?'+urlencode(params),
                          headers={'User-Agent':'SinyalAI-Benchmark/3.0'})
        try:
            payload = json.load(urlopen(request, timeout=20))
        except HTTPError as error:
            if error.code != 429:
                raise
            # Wikimedia random generators are rate-limited; respect Retry-After
            # when present and use bounded backoff instead of hammering the API.
            retry_after = error.headers.get('Retry-After')
            delay = int(retry_after) if retry_after and retry_after.isdigit() else 8
            print(f'  HTTP 429; waiting {delay}s before retry...', flush=True)
            time.sleep(delay)
            continue
        except URLError:
            time.sleep(3)
            continue
        for page in payload.get('query', {}).get('pages', []):
            topic = page.get('title','').strip()
            key = topic.casefold()
            if not topic or key in seen:
                continue
            text = clean_text(page.get('extract'))
            if len(text.split()) < 90:
                continue
            seen.add(key)
            rows.append({
                'id':'', 'label':'human', 'topic':topic, 'genre':genre, 'corpus':name,
                'text':text, 'source':page.get('fullurl',''),
                'revision':str(page.get('lastrevid','')), 'license':license_name,
                'generator':'human-public-corpus', 'requested_model':'', 'model':'',
                'prompt_id':'', 'generated_at':'', 'fallback':'false',
            })
            if len(rows) == PER_GENRE:
                return rows
        time.sleep(1.25)
    raise RuntimeError(f'{name}: collected only {len(rows)}/{PER_GENRE} new eligible topics')


def split_for(topic):
    digest = hashlib.sha256(f'{SPLIT_SALT}:{topic}'.encode()).digest()
    return 'holdout' if int.from_bytes(digest[:4], 'big') % 4 == 0 else 'calibration'


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8-sig') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def validate(rows):
    if len(rows) != 96 or len({row['topic'].casefold() for row in rows}) != 96:
        raise RuntimeError('v2 must contain exactly 96 unique human topics')
    counts = {genre:sum(row['genre']==genre for row in rows)
              for genre in sorted({row['genre'] for row in rows})}
    if set(counts.values()) != {PER_GENRE}:
        raise RuntimeError(f'Unbalanced genres: {counts}')
    if old_topics() & {row['topic'].casefold() for row in rows}:
        raise RuntimeError('v2 overlaps v1 topics')
    return counts


def main():
    if V2_HUMANS.exists() or V2_MANIFEST.exists():
        raise SystemExit('ERROR: v2 human corpus/manifest already exists; refusing to overwrite.')
    excluded = old_topics()
    rows = []
    for corpus in CORPORA:
        print(f'Collecting {PER_GENRE} new {corpus[1]} topics from {corpus[0]}...', flush=True)
        collected = collect_corpus(*corpus, excluded | {row['topic'].casefold() for row in rows})
        rows.extend(collected)
    rows.sort(key=lambda row: (row['genre'], row['topic']))
    for index, row in enumerate(rows, 1):
        row['id'] = f'human-v2-{index:03}'
    counts = validate(rows)
    manifest = {
        'version':2, 'created_before_ai_generation':True, 'split_salt':SPLIT_SALT,
        'method':'SHA-256 paired-topic 75/25 target',
        'topics':{row['topic']:split_for(row['topic']) for row in rows},
    }
    write_csv(V2_HUMANS, rows)
    V2_MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    split_counts = {name:sum(value==name for value in manifest['topics'].values())
                    for name in ('calibration','holdout')}
    print(json.dumps({'rows':len(rows),'genres':counts,'splits':split_counts,
                      'overlap_v1':0,'human_file':str(V2_HUMANS),
                      'manifest':str(V2_MANIFEST)}, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()