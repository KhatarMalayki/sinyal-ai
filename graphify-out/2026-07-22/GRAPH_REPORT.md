# Graph Report - tools ai  (2026-07-21)

## Corpus Check
- 29 files · ~13,944 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 160 nodes · 308 edges · 10 communities
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 5 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- app.js
- calibrate_features_v2.py
- calibrate_formula.py
- classification_metrics
- build_v2_dataset.py
- Benchmark Indonesia Multi-Genre
- generate_real_ai.py
- external_compare.py
- benchmark_expanded.py
- Benchmark Indonesia Sinyal.AI

## God Nodes (most connected - your core abstractions)
1. `classification_metrics()` - 20 edges
2. `Benchmark Indonesia Multi-Genre` - 14 edges
3. `score_text()` - 10 edges
4. `candidate_score()` - 8 edges
5. `main()` - 8 edges
6. `main()` - 7 edges
7. `analyzeText()` - 6 edges
8. `evaluate()` - 6 edges
9. `main()` - 6 edges
10. `features()` - 6 edges

## Surprising Connections (you probably didn't know these)
- `evaluate_frozen()` --calls--> `score_text()`  [EXTRACTED]
  calibrate_formula_v2.py → benchmark.py
- `score_local()` --calls--> `score_text()`  [EXTRACTED]
  external_compare.py → benchmark.py
- `cross_validate()` --calls--> `classification_metrics()`  [EXTRACTED]
  calibrate_features_v2.py → benchmark.py
- `threshold_metrics()` --calls--> `classification_metrics()`  [EXTRACTED]
  calibrate_features_v2.py → benchmark.py
- `best_threshold()` --calls--> `classification_metrics()`  [EXTRACTED]
  calibrate_formula.py → benchmark.py

## Import Cycles
- None detected.

## Communities (10 total, 0 thin omitted)

### Community 0 - "app.js"
Cohesion: 0.11
Nodes (26): analyzeBtn, analyzeSentenceContexts(), analyzeText(), applyRevisionBtn, charCount, clamp(), clearBtn, copyRevisionBtn (+18 more)

### Community 1 - "calibrate_features_v2.py"
Cohesion: 0.17
Nodes (21): best_threshold(), calibration_topics(), canonical_topic(), clamp(), coefficient_uniformity(), cross_validate(), features(), fold_map() (+13 more)

### Community 2 - "calibrate_formula.py"
Cohesion: 0.20
Nodes (19): best_threshold(), candidate_score(), clamp(), evaluate_frozen(), features(), load_rows(), Calibration-only formula selection with an explicit one-shot holdout gate.  `--s, select_and_freeze() (+11 more)

### Community 3 - "classification_metrics"
Cohesion: 0.19
Nodes (17): build_dataset(), clamp(), classification_metrics(), evaluate(), evaluate(), fetch_human_samples(), Reproducible Indonesian pilot benchmark for Sinyal.AI.  Human samples: Indonesia, read_dataset() (+9 more)

### Community 4 - "build_v2_dataset.py"
Cohesion: 0.23
Nodes (14): collect_corpus(), main(), old_topics(), Collect and freeze 96 new human topics plus a paired split manifest for v2., split_for(), validate(), write_csv(), main() (+6 more)

### Community 5 - "Benchmark Indonesia Multi-Genre"
Cohesion: 0.13
Nodes (14): Benchmark eksternal eksploratori 24 teks, Benchmark Indonesia Multi-Genre, Calibration formula lama; holdout tetap tertutup, Editor revisi lokal, Eksperimen formula calibration-only, Hasil, Keluarga fitur stilometrik baru (calibration-only), Keputusan dan tahap eksternal berikutnya (+6 more)

### Community 6 - "generate_real_ai.py"
Cohesion: 0.26
Nodes (13): api_request(), build_schedule(), clean(), extract_text(), generate(), main(), Generate real-model benchmark samples through an OpenAI-compatible API.  The API, Return field names/types only; never include generated text. (+5 more)

### Community 7 - "external_compare.py"
Cohesion: 0.47
Nodes (8): canonical(), collect(), exclusions(), generate(), Build and score a frozen 12-pair external detector comparison corpus., read(), score_local(), write()

### Community 8 - "benchmark_expanded.py"
Cohesion: 0.46
Nodes (7): build(), clean_text(), fetch_corpus(), generate_ai(), local_fallback(), Build a frozen multi-corpus Indonesian benchmark with auditable provenance., write_dataset()

### Community 9 - "Benchmark Indonesia Sinyal.AI"
Cohesion: 0.29
Nodes (6): Batasan, Benchmark Indonesia Sinyal.AI, Hasil pilot saat ini, Interpretasi dan keputusan, Menjalankan ulang, Sumber dan lisensi

## Knowledge Gaps
- **32 isolated node(s):** `input`, `wordCount`, `charCount`, `analyzeBtn`, `clearBtn` (+27 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `classification_metrics()` connect `classification_metrics` to `benchmark_expanded.py`, `calibrate_features_v2.py`, `calibrate_formula.py`, `external_compare.py`?**
  _High betweenness centrality (0.101) - this node is a cross-community bridge._
- **Why does `score_text()` connect `classification_metrics` to `benchmark_expanded.py`, `calibrate_formula.py`, `external_compare.py`?**
  _High betweenness centrality (0.012) - this node is a cross-community bridge._
- **Why does `evaluate()` connect `classification_metrics` to `benchmark_expanded.py`, `generate_real_ai.py`?**
  _High betweenness centrality (0.011) - this node is a cross-community bridge._
- **What connects `input`, `wordCount`, `charCount` to the rest of the system?**
  _32 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `app.js` be split into smaller, more focused modules?**
  _Cohesion score 0.11396011396011396 - nodes in this community are weakly interconnected._
- **Should `Benchmark Indonesia Multi-Genre` be split into smaller, more focused modules?**
  _Cohesion score 0.13333333333333333 - nodes in this community are weakly interconnected._