| metric | full @c36f6b9 (9 Nov, after #27/#28) | full @19eeaec (9 Nov) | full, pre-router (8 Nov) | no-tools | naive-rag-dense |
|---|---|---|---|---|---|
| routing | 94.0% (47/50), 95% CI 83.8-97.9% | 94.0% (47/50), 95% CI 83.8-97.9% | 90.0% (45/50), 95% CI 78.6-95.7% | 0.0% (0/50), 95% CI 0.0-7.1% | 0.0% (0/50), 95% CI 0.0-7.1% |
| safe_when_should_abstain | 100.0% (8/8), 95% CI 67.6-100.0% | 100.0% (8/8), 95% CI 67.6-100.0% | 75.0% (6/8), 95% CI 40.9-92.9% | 100.0% (8/8), 95% CI 67.6-100.0% | 75.0% (6/8), 95% CI 40.9-92.9% |
| answers_answerable | 71.4% (30/42), 95% CI 56.4-82.8% | 71.4% (30/42), 95% CI 56.4-82.8% | 76.2% (32/42), 95% CI 61.5-86.5% | 64.3% (27/42), 95% CI 49.2-77.0% | 64.3% (27/42), 95% CI 49.2-77.0% |
| cited_answer | 69.0% (29/42), 95% CI 54.0-80.9% | 69.0% (29/42), 95% CI 54.0-80.9% | 73.8% (31/42), 95% CI 58.9-84.7% | 0.0% (0/42), 95% CI 0.0-8.4% | 61.9% (26/42), 95% CI 46.8-75.0% |
| not_stale | 42.9% (3/7), 95% CI 15.8-75.0% | 57.1% (4/7), 95% CI 25.0-84.2% | 71.4% (5/7), 95% CI 35.9-91.8% | 71.4% (5/7), 95% CI 35.9-91.8% | 85.7% (6/7), 95% CI 48.7-97.4% |
| price_correct | 76.2% (16/21), 95% CI 54.9-89.4% | 61.9% (13/21), 95% CI 40.9-79.2% | 71.4% (15/21), 95% CI 50.0-86.2% | 0.0% (0/21), 95% CI 0.0-15.5% | 0.0% (0/21), 95% CI 0.0-15.5% |

Paired vs **full @c36f6b9** (exact McNemar, two-sided; only questions where the two differ count):

| metric | system | n | only ref right | only system right | p |
|---|---|---|---|---|---|
| routing | full @19eeaec (9 Nov) | 50 | 0 | 0 | 1 |
| routing | full, pre-router (8 Nov) | 50 | 2 | 0 | 0.5 |
| routing | no-tools | 50 | 47 | 0 | 1.42e-14 |
| routing | naive-rag-dense | 50 | 47 | 0 | 1.42e-14 |
| safe_when_should_abstain | full @19eeaec (9 Nov) | 8 | 0 | 0 | 1 |
| safe_when_should_abstain | full, pre-router (8 Nov) | 8 | 2 | 0 | 0.5 |
| safe_when_should_abstain | no-tools | 8 | 0 | 0 | 1 |
| safe_when_should_abstain | naive-rag-dense | 8 | 2 | 0 | 0.5 |
| answers_answerable | full @19eeaec (9 Nov) | 42 | 3 | 3 | 1 |
| answers_answerable | full, pre-router (8 Nov) | 42 | 3 | 5 | 0.727 |
| answers_answerable | no-tools | 42 | 14 | 11 | 0.69 |
| answers_answerable | naive-rag-dense | 42 | 13 | 10 | 0.678 |
| cited_answer | full @19eeaec (9 Nov) | 42 | 3 | 3 | 1 |
| cited_answer | full, pre-router (8 Nov) | 42 | 3 | 5 | 0.727 |
| cited_answer | no-tools | 42 | 29 | 0 | 3.73e-09 |
| cited_answer | naive-rag-dense | 42 | 14 | 11 | 0.69 |
| not_stale | full @19eeaec (9 Nov) | 7 | 0 | 1 | 1 |
| not_stale | full, pre-router (8 Nov) | 7 | 0 | 2 | 0.5 |
| not_stale | no-tools | 7 | 1 | 3 | 0.625 |
| not_stale | naive-rag-dense | 7 | 0 | 3 | 0.25 |
| price_correct | full @19eeaec (9 Nov) | 21 | 4 | 1 | 0.375 |
| price_correct | full, pre-router (8 Nov) | 21 | 4 | 3 | 1 |
| price_correct | no-tools | 21 | 16 | 0 | 3.05e-05 |
| price_correct | naive-rag-dense | 21 | 16 | 0 | 3.05e-05 |

Files: 20261109T142139Z_full_dev_metrics.json (@c36f6b9), 20261109T112136Z_full_dev_metrics.json, 20261108T151811Z_full_dev_metrics.json, 20261108T003712Z_no-tools_dev_metrics.json, 20261108T134207Z_naive-rag-dense_dev_metrics.json
