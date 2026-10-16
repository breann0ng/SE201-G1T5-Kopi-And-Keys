"""PLACEHOLDER: run a labelled question set through the graph and log results.

Intended usage:
    python -m kopi_keys.evaluation.run_eval --set development

Plan:
1. Load data/evaluation/<set>/*.jsonl.
2. For each question, call `kopi_keys.graph.run_graph` and keep the full final
   state (route, passages, price_result, draft, verification errors, trace).
3. Score with `metrics.py`; write per-question rows plus a failure log tagged
   by stage (routing, retrieval, synthesis, citation, SQL, abstention) to
   .local/reports/.
4. Run the same set through `baselines.py` for comparison.

Never run the held-out set while tuning.
"""


def main() -> int:
    raise NotImplementedError("The evaluation runner has not been built yet.")


if __name__ == "__main__":
    raise SystemExit(main())
