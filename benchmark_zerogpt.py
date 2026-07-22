"""Run the frozen 24-text external corpus through ZeroGPT's public endpoint."""
from __future__ import annotations

import csv, json, math, time
from pathlib import Path
from urllib.request import Request, urlopen

from benchmark import classification_metrics

ROOT = Path(__file__).parent
OUT = ROOT / 'benchmark' / 'expanded'
DATA = OUT / 'external-comparison-dataset.csv'
RESULTS = OUT / 'external-comparison-zerogpt.csv'
REPORT = OUT / 'external-comparison-zerogpt-report.json'
ENDPOINT = 'https://api.zerogpt.com/api/detect/detectText'


def read_csv(path):
    with path.open(newline='', encoding='utf-8-sig') as file:
        return list(csv.DictReader(file))


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8-sig') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def detect(text):
    body = json.dumps({'input_text':text}).encode()
    request = Request(ENDPOINT, data=body, method='POST', headers={
        'Content-Type':'application/json', 'Accept':'application/json',
        'Origin':'https://www.zerogpt.com', 'Referer':'https://www.zerogpt.com/',
        'User-Agent':'Mozilla/5.0 SinyalAI-External-Benchmark/1.0',
    })
    with urlopen(request, timeout=60) as response:
        payload = json.load(response)
    if not payload.get('success') or not isinstance(payload.get('data'), dict):
        raise RuntimeError(f'Invalid ZeroGPT response: {payload}')
    return payload['data']


def main():
    rows = read_csv(DATA)
    done = read_csv(RESULTS) if RESULTS.exists() else []
    if [r['id'] for r in done] != [r['id'] for r in rows[:len(done)]]:
        raise RuntimeError('ZeroGPT checkpoint order mismatch')
    for index, row in enumerate(rows[len(done):], len(done) + 1):
        print(f'[{index:02}/24] {row["id"]}', flush=True)
        try:
            data = detect(row['text'])
            score = float(data.get('fakePercentage', 0))
            done.append({'id':row['id'], 'label':row['label'], 'topic':row['topic'],
                         'genre':row['genre'], 'tool':'zerogpt', 'score':score,
                         'decision':'ai' if score >= 50 else 'human', 'covered':'true',
                         'feedback':data.get('feedback',''),
                         'detected_language':data.get('detected_language',''),
                         'text_words':data.get('textWords',''), 'ai_words':data.get('aiWords',''),
                         'error':''})
        except Exception as error:
            done.append({'id':row['id'], 'label':row['label'], 'topic':row['topic'],
                         'genre':row['genre'], 'tool':'zerogpt', 'score':'',
                         'decision':'', 'covered':'false', 'feedback':'',
                         'detected_language':'', 'text_words':'', 'ai_words':'',
                         'error':str(error)})
        write_csv(RESULTS, done); time.sleep(1.2)
    covered = [r for r in done if r['covered'] == 'true']
    prepared = [{**r, 'score':float(r['score'])} for r in covered]
    metric = classification_metrics(prepared, 50) if covered else {}
    report = {'tool':'zerogpt', 'rows':len(done), 'covered':len(covered),
              'coverage':len(covered)/len(done), 'metrics_on_covered':metric,
              'method':'public web endpoint observed from anonymous ZeroGPT UI; one request per frozen document'}
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()