| metric | full | full | no-tools | naive-rag-dense |
|---|---|---|---|---|
| routing | 94.0% (47/50), 95% CI 83.8-97.9% | 94.0% (47/50), 95% CI 83.8-97.9% | 0.0% (0/50), 95% CI 0.0-7.1% | 0.0% (0/50), 95% CI 0.0-7.1% |
| safe_when_should_abstain | 100.0% (8/8), 95% CI 67.6-100.0% | 100.0% (8/8), 95% CI 67.6-100.0% | 87.5% (7/8), 95% CI 52.9-97.8% | 87.5% (7/8), 95% CI 52.9-97.8% |
| answers_answerable | 73.8% (31/42), 95% CI 58.9-84.7% | 73.8% (31/42), 95% CI 58.9-84.7% | 61.9% (26/42), 95% CI 46.8-75.0% | 61.9% (26/42), 95% CI 46.8-75.0% |
| cited_answer | 71.4% (30/42), 95% CI 56.4-82.8% | 71.4% (30/42), 95% CI 56.4-82.8% | 0.0% (0/42), 95% CI 0.0-8.4% | 61.9% (26/42), 95% CI 46.8-75.0% |
| not_stale | 57.1% (4/7), 95% CI 25.0-84.2% | 57.1% (4/7), 95% CI 25.0-84.2% | 71.4% (5/7), 95% CI 35.9-91.8% | 85.7% (6/7), 95% CI 48.7-97.4% |
| price_correct | 85.7% (18/21), 95% CI 65.4-95.0% | 85.7% (18/21), 95% CI 65.4-95.0% | 0.0% (0/21), 95% CI 0.0-15.5% | 0.0% (0/21), 95% CI 0.0-15.5% |

Paired vs **full** (exact McNemar, two-sided; only questions where the two differ count):

| metric | system | n | only ref right | only system right | p |
|---|---|---|---|---|---|
| routing | full | 50 | 0 | 0 | 1 |
| routing | no-tools | 50 | 47 | 0 | 1.42e-14 |
| routing | naive-rag-dense | 50 | 47 | 0 | 1.42e-14 |
| safe_when_should_abstain | full | 8 | 0 | 0 | 1 |
| safe_when_should_abstain | no-tools | 8 | 1 | 0 | 1 |
| safe_when_should_abstain | naive-rag-dense | 8 | 1 | 0 | 1 |
| answers_answerable | full | 42 | 0 | 0 | 1 |
| answers_answerable | no-tools | 42 | 13 | 8 | 0.383 |
| answers_answerable | naive-rag-dense | 42 | 15 | 10 | 0.424 |
| cited_answer | full | 42 | 0 | 0 | 1 |
| cited_answer | no-tools | 42 | 30 | 0 | 1.86e-09 |
| cited_answer | naive-rag-dense | 42 | 15 | 11 | 0.557 |
| not_stale | full | 7 | 0 | 0 | 1 |
| not_stale | no-tools | 7 | 1 | 2 | 1 |
| not_stale | naive-rag-dense | 7 | 0 | 2 | 0.5 |
| price_correct | full | 21 | 0 | 0 | 1 |
| price_correct | no-tools | 21 | 18 | 0 | 7.63e-06 |
| price_correct | naive-rag-dense | 21 | 18 | 0 | 7.63e-06 |

Files: 20261109T182959Z_full_dev_metrics.json, 20261109T184200Z_full_dev_metrics.json, 20261109T183455Z_no-tools_dev_metrics.json, 20261109T183743Z_naive-rag-dense_dev_metrics.json
