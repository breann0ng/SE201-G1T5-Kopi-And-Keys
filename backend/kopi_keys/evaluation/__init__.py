"""Evaluation harness (proposal section 4 and Appendix E). See README.md.

dataset.py    load, validate and resolve the labelled question sets; regenerate Stage 1 labels
metrics.py    one function per Appendix E metric that can be computed deterministically
baselines.py  retrievers to score; answer-level baselines (TODO)
run_eval.py   python -m kopi_keys.evaluation.run_eval
"""
