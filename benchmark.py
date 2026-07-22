"""Reproducible Indonesian pilot benchmark for Sinyal.AI.

Human samples: Indonesian Wikipedia introductions (CC BY-SA 4.0).
AI samples: deterministic synthetic expository passages paired by topic.
The scoring function mirrors the frozen app.js v3.0 stylometric formula.
"""
from __future__ import annotations

import csv
import argparse
import json
import math
import random
import re
from pathlib import Path
from statistics import mean, pvariance
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).parent
OUT = ROOT / "benchmark"
DATA = OUT / "dataset.csv"
RESULTS = OUT / "results.csv"
REPORT = OUT / "report.json"
API = "https://id.wikipedia.org/w/api.php"
SEED = 20260719
COUNT = 25
UI_THRESHOLD = 50
CALIBRATION_FRACTION = .6


def words(text):
    return re.findall(r"[a-zà-ÿ0-9]+(?:['’-][a-zà-ÿ]+)*", text.lower(), re.I)


def clamp(value, low=0, high=1):
    return min(high, max(low, value))


def variance(values):
    return pvariance(values) if values else 0


def score_text(text):
    ws = words(text)
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    if len(sentences) < 2:
        sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    lengths = [len(words(s)) for s in sentences if words(s)]
    paragraph_lengths = [len(words(p)) for p in paragraphs]
    commas = [sentence.count(',') for sentence in sentences]
    closure_rate = sum(sentence.rstrip().endswith(('.', '!', '?')) for sentence in sentences) / max(len(sentences), 1)

    def uniformity(values, scale=1, fallback=.35):
        if len(values) < 2:
            return fallback
        return 1 - clamp(math.sqrt(variance(values)) / max(mean(values) * scale, 1))

    function_words = {'yang','dan','di','ke','dari','untuk','dengan','pada','dalam',
                      'oleh','karena','agar','tetapi','juga','atau','sebagai','itu','ini'}
    size = max(1, math.ceil(len(ws) / 4))
    chunks = [ws[index:index+size] for index in range(0, len(ws), size)] or [[]]
    function_rates = [sum(word in function_words for word in chunk) / max(len(chunk), 1)
                      for chunk in chunks]
    lexical_rates = [len(set(chunk)) / max(len(chunk), 1) for chunk in chunks]
    feature = {
        'sentence_uniformity':uniformity(lengths, .72),
        'paragraph_uniformity':uniformity(paragraph_lengths, .85),
        'sentence_closure':clamp((closure_rate-.45)/.55),
        'comma_uniformity':uniformity(commas, 1.15),
        'function_stability':uniformity(function_rates, 2.1),
        'lexical_stability':uniformity(lexical_rates, 2.0),
        'digit_density':clamp(sum(char.isdigit() for char in text)/max(len(text),1)*35),
        'quote_density':clamp(sum(char in '"“”‘’' for char in text)/max(len(text),1)*55),
    }
    raw = (feature['sentence_uniformity']*.26 + feature['paragraph_uniformity']*.10 +
           feature['sentence_closure']*.18 + feature['comma_uniformity']*.12 +
           feature['function_stability']*.15 + feature['lexical_stability']*.09 -
           feature['digit_density']*.05 - feature['quote_density']*.05)
    return math.floor(clamp(100 / (1 + math.exp(-12 * (raw-.5435406480407824))), 1, 99))


def fetch_human_samples():
    rows = []
    seen = set()
    for _ in range(20):
        params = {'action':'query','generator':'random','grnnamespace':0,'grnlimit':50,
                  'prop':'extracts|info','inprop':'url','explaintext':1,'exintro':1,
                  'format':'json','formatversion':2}
        req = Request(API + '?' + urlencode(params), headers={'User-Agent':'SinyalAI-Benchmark/1.0'})
        pages = json.load(urlopen(req, timeout=30))['query']['pages']
        for page in pages:
            if page['pageid'] in seen:
                continue
            seen.add(page['pageid'])
            clean = re.sub(r'\s+', ' ', page.get('extract', '')).strip()
            ws = words(clean)
            if len(ws) < 90:
                continue
            text = ' '.join(ws[:140])
            rows.append({'id':f'human-{len(rows)+1:02}', 'label':'human', 'topic':page['title'],
                         'text':text, 'source':page['fullurl'], 'revision':page.get('lastrevid',''),
                         'license':'CC BY-SA 4.0'})
            if len(rows) == COUNT:
                return rows
    if len(rows) < COUNT:
        raise RuntimeError(f'Only {len(rows)} eligible Wikipedia samples found after 20 batches.')


def synthetic_ai(topic, index):
    templates = [
        "{t} merupakan topik yang memiliki peran penting dalam perkembangan pengetahuan dan kehidupan masyarakat. Pembahasan mengenai topik ini dapat membantu pembaca memahami latar belakang, fungsi, serta pengaruhnya dalam berbagai bidang. Selain itu, informasi yang tersusun secara sistematis memungkinkan proses pembelajaran berlangsung lebih efektif dan terarah.",
        "Dalam penerapannya, {t} tidak hanya menawarkan sejumlah manfaat, tetapi juga menghadirkan tantangan yang perlu diperhatikan. Data yang akurat, metode yang tepat, dan kerja sama antarpihak dapat meningkatkan kualitas keputusan. Oleh karena itu, setiap langkah perlu dilakukan secara bertanggung jawab agar hasilnya memberikan dampak yang positif.",
        "Secara keseluruhan, pemahaman tentang {t} perlu terus dikembangkan melalui penelitian, pendidikan, dan penyebaran informasi yang dapat dipercaya. Pendekatan tersebut mampu mengurangi kesalahpahaman sekaligus membuka peluang baru. Dengan demikian, masyarakat dapat memanfaatkan pengetahuan yang tersedia secara lebih bijak, inklusif, dan berkelanjutan."
    ]
    # Deterministic variation in paragraph order without changing provenance.
    order = [index % 3, (index + 1) % 3, (index + 2) % 3]
    return '\n\n'.join(templates[i].format(t=topic) for i in order)


def read_dataset():
    with DATA.open(newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    required = {'id', 'label', 'topic', 'text', 'source', 'revision', 'license'}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f'{DATA} is empty or has an invalid schema.')
    if len({row['id'] for row in rows}) != len(rows):
        raise ValueError(f'{DATA} contains duplicate IDs.')
    return rows


def build_dataset(refresh=False):
    if DATA.exists() and not refresh:
        return read_dataset()
    random.seed(SEED)
    humans = fetch_human_samples()
    ais = [{'id':f'ai-{i+1:02}', 'label':'ai', 'topic':row['topic'],
            'text':synthetic_ai(row['topic'], i), 'source':'local deterministic generator',
            'revision':'generator-v1', 'license':'Generated for benchmark'}
           for i, row in enumerate(humans)]
    rows = humans + ais
    OUT.mkdir(exist_ok=True)
    with DATA.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    return rows


def classification_metrics(scored, threshold):
    tp = sum(r['label']=='ai' and r['score']>=threshold for r in scored)
    tn = sum(r['label']=='human' and r['score']<threshold for r in scored)
    fp = sum(r['label']=='human' and r['score']>=threshold for r in scored)
    fn = sum(r['label']=='ai' and r['score']<threshold for r in scored)
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    specificity = tn / (tn + fp) if tn + fp else 0
    f1 = 2*precision*recall / (precision + recall) if precision + recall else 0
    denominator = math.sqrt((tp+fp)*(tp+fn)*(tn+fp)*(tn+fn))
    return {
        'threshold': threshold, 'tp': tp, 'tn': tn, 'fp': fp, 'fn': fn,
        'accuracy': (tp+tn)/len(scored) if scored else 0,
        'precision': precision, 'recall': recall, 'specificity': specificity,
        'false_positive_rate': 1-specificity,
        'balanced_accuracy': (recall+specificity)/2,
        'f1': f1, 'mcc': ((tp*tn)-(fp*fn))/denominator if denominator else 0
    }


def select_threshold(scored):
    best = None
    for threshold in range(5, 96):
        metric = classification_metrics(scored, threshold)
        if best is None or (metric['f1'], metric['accuracy']) > (best['f1'], best['accuracy']):
            best = metric
    return best


def evaluate(rows):
    topics = sorted({row['topic'] for row in rows})
    random.Random(SEED).shuffle(topics)
    calibration_count = round(len(topics) * CALIBRATION_FRACTION)
    calibration_topics = set(topics[:calibration_count])
    scored = [{**row, 'score':score_text(row['text']),
               'split':'calibration' if row['topic'] in calibration_topics else 'test'}
              for row in rows]
    calibration = [row for row in scored if row['split'] == 'calibration']
    test = [row for row in scored if row['split'] == 'test']
    selected = select_threshold(calibration)
    with RESULTS.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['id','label','topic','split','score','source'])
        writer.writeheader(); writer.writerows({k:r[k] for k in writer.fieldnames} for r in scored)
    report = {'dataset_size':len(scored),
              'human_samples':sum(r['label']=='human' for r in scored),
              'ai_samples':sum(r['label']=='ai' for r in scored),
              'seed':SEED, 'ui_threshold':classification_metrics(scored, UI_THRESHOLD),
              'split':{'method':'paired topic split','calibration_topics':len(calibration_topics),
                       'test_topics':len(topics)-len(calibration_topics),
                       'calibration_samples':len(calibration),'test_samples':len(test)},
              'calibration_best':selected,
              'held_out_test':classification_metrics(test, selected['threshold']),
              'score_summary':{
                  label:{'min':min(r['score'] for r in scored if r['label']==label),
                         'mean':round(mean(r['score'] for r in scored if r['label']==label),2),
                         'max':max(r['score'] for r in scored if r['label']==label)}
                  for label in ('human','ai')}}
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true',
                        help='Fetch a new random Wikipedia dataset and overwrite dataset.csv.')
    args = parser.parse_args()
    result = evaluate(build_dataset(refresh=args.refresh))
    print(json.dumps(result, indent=2, ensure_ascii=False))