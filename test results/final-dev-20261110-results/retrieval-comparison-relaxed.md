| metric | hybrid relaxed (20261109T182816Z) | bm25 relaxed (20261109T182818Z) | dense relaxed (20261109T182824Z) |
|---|---|---|---|
| hit@5 all | 75.9% (22/29), 95% CI 57.9-87.8% | 55.2% (16/29), 95% CI 37.5-71.6% | 69.0% (20/29), 95% CI 50.8-82.7% |
| hit@5 policy | 90.9% (20/22), 95% CI 72.2-97.5% | 68.2% (15/22), 95% CI 47.3-83.6% | 81.8% (18/22), 95% CI 61.5-92.7% |
| hit@5 discovery | 28.6% (2/7), 95% CI 8.2-64.1% | 14.3% (1/7), 95% CI 2.6-51.3% | 28.6% (2/7), 95% CI 8.2-64.1% |

Paired vs **hybrid relaxed (20261109T182816Z)** (exact McNemar, two-sided; only questions where the two differ count):

| metric | system | n | only ref right | only system right | p |
|---|---|---|---|---|---|
| hit@5 all | bm25 relaxed (20261109T182818Z) | 29 | 7 | 1 | 0.0703 |
| hit@5 all | dense relaxed (20261109T182824Z) | 29 | 2 | 0 | 0.5 |
| hit@5 policy | bm25 relaxed (20261109T182818Z) | 22 | 6 | 1 | 0.125 |
| hit@5 policy | dense relaxed (20261109T182824Z) | 22 | 2 | 0 | 0.5 |
| hit@5 discovery | bm25 relaxed (20261109T182818Z) | 7 | 1 | 0 | 1 |
| hit@5 discovery | dense relaxed (20261109T182824Z) | 7 | 0 | 0 | 1 |

Files: 20261109T182816Z_retrieval_hybrid_final_dev.json, 20261109T182818Z_retrieval_bm25_final_dev.json, 20261109T182824Z_retrieval_dense_final_dev.json
