| metric | full | no-tools | naive-rag-dense |
|---|---|---|---|
| routing | 90.0% (45/50), 95% CI 78.6-95.7% | 0.0% (0/50), 95% CI 0.0-7.1% | 0.0% (0/50), 95% CI 0.0-7.1% |
| safe_when_should_abstain | 75.0% (6/8), 95% CI 40.9-92.9% | 100.0% (8/8), 95% CI 67.6-100.0% | 75.0% (6/8), 95% CI 40.9-92.9% |
| answers_answerable | 76.2% (32/42), 95% CI 61.5-86.5% | 64.3% (27/42), 95% CI 49.2-77.0% | 64.3% (27/42), 95% CI 49.2-77.0% |
| cited_answer | 73.8% (31/42), 95% CI 58.9-84.7% | 0.0% (0/42), 95% CI 0.0-8.4% | 61.9% (26/42), 95% CI 46.8-75.0% |
| not_stale | 71.4% (5/7), 95% CI 35.9-91.8% | 71.4% (5/7), 95% CI 35.9-91.8% | 85.7% (6/7), 95% CI 48.7-97.4% |
| price_correct | 71.4% (15/21), 95% CI 50.0-86.2% | 0.0% (0/21), 95% CI 0.0-15.5% | 0.0% (0/21), 95% CI 0.0-15.5% |

Paired vs **full** (exact McNemar, two-sided; only questions where the two differ count):

| metric | system | n | only ref right | only system right | p |
|---|---|---|---|---|---|
| routing | no-tools | 50 | 45 | 0 | 5.68e-14 |
| routing | naive-rag-dense | 50 | 45 | 0 | 5.68e-14 |
| safe_when_should_abstain | no-tools | 8 | 0 | 2 | 0.5 |
| safe_when_should_abstain | naive-rag-dense | 8 | 2 | 2 | 1 |
| answers_answerable | no-tools | 42 | 14 | 9 | 0.405 |
| answers_answerable | naive-rag-dense | 42 | 14 | 9 | 0.405 |
| cited_answer | no-tools | 42 | 31 | 0 | 9.31e-10 |
| cited_answer | naive-rag-dense | 42 | 15 | 10 | 0.424 |
| not_stale | no-tools | 7 | 1 | 1 | 1 |
| not_stale | naive-rag-dense | 7 | 1 | 2 | 1 |
| price_correct | no-tools | 21 | 15 | 0 | 6.1e-05 |
| price_correct | naive-rag-dense | 21 | 15 | 0 | 6.1e-05 |

Files: 20261108T151811Z_full_dev_metrics.json, 20261108T003712Z_no-tools_dev_metrics.json, 20261108T134207Z_naive-rag-dense_dev_metrics.json
