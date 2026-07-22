"""Build a frozen multi-corpus Indonesian benchmark with auditable provenance."""
from __future__ import annotations

import argparse
import csv
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from benchmark import SEED, classification_metrics, score_text, select_threshold

ROOT = Path(__file__).parent
OUT = ROOT / 'benchmark' / 'expanded'
DATA = OUT / 'dataset.csv'
RESULTS = OUT / 'results.csv'
REPORT = OUT / 'report.json'
PER_SOURCE = 8
MIN_WORDS = 90
MAX_WORDS = 180

CORPORA = [
    ('wikipedia', 'ensiklopedis', 'https://id.wikipedia.org/w/api.php', 'CC BY-SA 4.0'),
    ('wikibooks', 'instruksional', 'https://id.wikibooks.org/w/api.php', 'CC BY-SA 4.0'),
    ('wikisource', 'dokumen_sastra', 'https://id.wikisource.org/w/api.php', 'CC BY-SA 4.0'),
]
MODELS = ['openai', 'mistral', 'qwen-coder']
PROMPTS = {
    'ensiklopedis': 'Tulis uraian ensiklopedis bahasa Indonesia tentang {topic}.',
    'instruksional': 'Tulis panduan praktis bahasa Indonesia tentang {topic}, dengan langkah yang mengalir alami.',
    'dokumen_sastra': 'Tulis prosa naratif bahasa Indonesia yang terinspirasi tema {topic}, tanpa mengutip sumber.',
}


def clean_text(text):
    text = re.sub(r'\s+', ' ', text or '').strip()
    tokens = re.findall(r"\S+", text)
    return ' '.join(tokens[:MAX_WORDS])


def fetch_corpus(name, genre, api, license_name):
    rows, seen = [], set()
    for _ in range(15):
        params = {'action':'query','generator':'random','grnnamespace':0,'grnlimit':20,
                  'prop':'extracts|info','inprop':'url','explaintext':1,'exintro':1,
                  'format':'json','formatversion':2}
        req = Request(api+'?'+urlencode(params), headers={'User-Agent':'SinyalAI-Benchmark/2.0'})
        payload = json.load(urlopen(req, timeout=12))
        for page in payload.get('query', {}).get('pages', []):
            if page.get('pageid') in seen:
                continue
            seen.add(page.get('pageid'))
            text = clean_text(page.get('extract'))
            if len(text.split()) < MIN_WORDS:
                continue
            rows.append({'id':'', 'label':'human', 'topic':page['title'], 'genre':genre,
                         'corpus':name, 'text':text, 'source':page.get('fullurl',''),
                         'revision':str(page.get('lastrevid','')), 'license':license_name,
                         'generator':'human-public-corpus', 'model':'', 'prompt_id':'',
                         'generated_at':'', 'fallback':'false'})
            if len(rows) == PER_SOURCE:
                return rows
    raise RuntimeError(f'{name}: only {len(rows)} eligible samples collected')


def local_fallback(topic, genre, index):
    variants = {
        'ensiklopedis': f'{topic} merupakan pokok bahasan yang dapat dilihat dari sejarah, fungsi, dan pengaruhnya. Pemahaman yang baik memerlukan penjelasan konteks, istilah utama, serta hubungan dengan masyarakat. Berbagai sumber dapat dibandingkan agar gambaran yang diperoleh tidak hanya lengkap, tetapi juga seimbang. Dalam perkembangannya, pembahasan mengenai {topic} berubah mengikuti temuan dan kebutuhan baru. Karena itu, informasi perlu diperiksa secara berkala dan disampaikan dengan bahasa yang jelas. Pendekatan tersebut membantu pembaca membedakan fakta, penafsiran, dan hal yang masih diperdebatkan.',
        'instruksional': f'Untuk mulai mempelajari {topic}, siapkan tujuan yang sederhana dan catat hasil setiap percobaan. Mulailah dari bagian paling dasar, lalu kerjakan satu langkah pada satu waktu. Jika hasilnya belum sesuai, periksa kembali bahan, urutan, dan asumsi yang digunakan. Setelah itu, ulangi dengan perubahan kecil agar penyebab perbedaan mudah diketahui. Simpan contoh yang berhasil sebagai acuan. Cara bertahap ini membuat proses belajar lebih aman, mudah dievaluasi, dan dapat disesuaikan dengan kebutuhan.',
        'dokumen_sastra': f'Pagi itu, nama {topic} muncul lagi dalam buku tua yang ditemukan Raka di lemari belakang. Ia membacanya perlahan sambil mendengar hujan menyentuh atap. Tidak ada penjelasan yang benar-benar lengkap, hanya catatan pendek dan sebuah tanggal yang hampir pudar. Raka membawa buku itu ke beranda dan bertanya kepada neneknya. Nenek tersenyum, lalu mulai bercerita tentang perjalanan yang lama disimpan keluarga. Menjelang sore, Raka memahami bahwa cerita tersebut bukan sekadar kenangan, melainkan pesan agar ia berani menentukan langkahnya sendiri.'
    }
    return variants[genre]


def generate_ai(human, index):
    model = MODELS[index % len(MODELS)]
    prompt_id = f"{human['genre']}-v1"
    prompt = PROMPTS[human['genre']].format(topic=human['topic']) + ' Panjang 120–170 kata. Keluarkan hanya teks.'
    endpoint = 'https://text.pollinations.ai/' + quote(prompt) + '?' + urlencode({'model':model,'seed':SEED+index})
    fallback = False
    try:
        req = Request(endpoint, headers={'User-Agent':'SinyalAI-Benchmark/2.0'})
        text = clean_text(urlopen(req, timeout=12).read().decode('utf-8'))
        if len(text.split()) < 80:
            raise ValueError('response too short')
        generator = 'Pollinations text API'
    except Exception:
        text = local_fallback(human['topic'], human['genre'], index)
        generator, model, fallback = 'local multi-style fallback-v1', 'local-fallback-v1', True
    return {'id':'', 'label':'ai', 'topic':human['topic'], 'genre':human['genre'],
            'corpus':human['corpus'], 'text':text, 'source':endpoint,
            'revision':'', 'license':'Generated benchmark sample', 'generator':generator,
            'model':model, 'prompt_id':prompt_id,
            'generated_at':datetime.now(timezone.utc).isoformat(),
            'fallback':str(fallback).lower()}


def write_dataset(rows):
    OUT.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with DATA.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def build(refresh=False):
    if DATA.exists() and not refresh:
        with DATA.open(newline='', encoding='utf-8-sig') as f:
            rows = list(csv.DictReader(f))
        changed = False
        for row in rows:
            if row['fallback'] == 'true' and row['model'] != 'local-fallback-v1':
                row['model'] = 'local-fallback-v1'
                changed = True
        if changed:
            write_dataset(rows)
        return rows
    humans = []
    for corpus in CORPORA:
        humans.extend(fetch_corpus(*corpus))
    with ThreadPoolExecutor(max_workers=8) as pool:
        ais = list(pool.map(lambda item: generate_ai(item[1], item[0]), enumerate(humans)))
    rows = humans + ais
    for index, row in enumerate(rows, 1):
        row['id'] = f"{row['label']}-{index:03}"
    write_dataset(rows)
    return rows


def evaluate(rows):
    topics = sorted({r['topic'] for r in rows})
    test_topics = {topic for i, topic in enumerate(topics) if i % 5 in (0, 1)}
    scored = [{**r, 'score':score_text(r['text']),
               'split':'test' if r['topic'] in test_topics else 'calibration'} for r in rows]
    calibration = [r for r in scored if r['split']=='calibration']
    test = [r for r in scored if r['split']=='test']
    selected = select_threshold(calibration)
    fields = ['id','label','topic','genre','corpus','requested_model','model','generator',
              'fallback','split','score','source']
    for row in scored:
        row.setdefault('requested_model', '')
    with RESULTS.open('w', newline='', encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader(); writer.writerows({k:r[k] for k in fields} for r in scored)
    def grouped(field):
        return {value:classification_metrics([r for r in scored if r[field]==value],70)
                for value in sorted({r[field] for r in scored})}
    report = {'dataset_size':len(scored), 'ui_threshold':classification_metrics(scored,70),
              'selected_on_calibration':selected,
              'held_out_test':classification_metrics(test,selected['threshold']),
              'split':{'calibration':len(calibration),'test':len(test),'method':'topic hash-free deterministic 60/40'},
              'by_genre_at_70':grouped('genre'), 'by_corpus_at_70':grouped('corpus'),
              'ai_by_requested_model_at_70':{
                  m:classification_metrics([r for r in scored if r['label']=='ai' and
                                             r.get('requested_model')==m],70)
                  for m in sorted({r.get('requested_model','') for r in scored
                                   if r['label']=='ai' and r.get('requested_model')})},
              'ai_by_model_at_70':{m:classification_metrics([r for r in scored if r['label']=='ai' and r['model']==m],70)
                                   for m in sorted({r['model'] for r in scored if r['label']=='ai'})},
              'fallback_ai_samples':sum(r['label']=='ai' and r['fallback']=='true' for r in scored)}
    REPORT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--refresh',action='store_true'); args=parser.parse_args()
    print(json.dumps(evaluate(build(args.refresh)),indent=2,ensure_ascii=False))