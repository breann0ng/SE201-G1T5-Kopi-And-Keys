| metric | hybrid (20261109T182816Z) | bm25 (20261109T182818Z) | dense (20261109T182824Z) |
|---|---|---|---|
| hit@5 all | 69.0% (20/29), 95% CI 50.8-82.7% | 51.7% (15/29), 95% CI 34.4-68.6% | 62.1% (18/29), 95% CI 44.0-77.3% |
| hit@5 policy | 81.8% (18/22), 95% CI 61.5-92.7% | 63.6% (14/22), 95% CI 43.0-80.3% | 72.7% (16/22), 95% CI 51.8-86.8% |
| hit@5 discovery | 28.6% (2/7), 95% CI 8.2-64.1% | 14.3% (1/7), 95% CI 2.6-51.3% | 28.6% (2/7), 95% CI 8.2-64.1% |

Paired vs **hybrid (20261109T182816Z)** (exact McNemar, two-sided; only questions where the two differ count):

| metric | system | n | only ref right | only system right | p |
|---|---|---|---|---|---|
| hit@5 all | bm25 (20261109T182818Z) | 29 | 7 | 2 | 0.18 |
| hit@5 all | dense (20261109T182824Z) | 29 | 2 | 0 | 0.5 |
| hit@5 policy | bm25 (20261109T182818Z) | 22 | 6 | 2 | 0.289 |
| hit@5 policy | dense (20261109T182824Z) | 22 | 2 | 0 | 0.5 |
| hit@5 discovery | bm25 (20261109T182818Z) | 7 | 1 | 0 | 1 |
| hit@5 discovery | dense (20261109T182824Z) | 7 | 0 | 0 | 1 |

Files: 20261109T182816Z_retrieval_hybrid_final_dev.json, 20261109T182818Z_retrieval_bm25_final_dev.json, 20261109T182824Z_retrieval_dense_final_dev.json
