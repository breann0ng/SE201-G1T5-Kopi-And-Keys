"""Build the Policy Vector Index (ChromaDB) for the ACTIVE policy snapshot.

Needs Ollama running with the embedding model pulled:
    ollama pull embeddinggemma
    .\\.venv\\Scripts\\python.exe -m pip install -e ".[dev,rag]"
    .\\.venv\\Scripts\\python.exe scripts/build_policy_index.py

Writes data/chroma/ (gitignored). Rebuild whenever data/policy_snapshots/ACTIVE
changes or the chunks are regenerated. Takes a few minutes on CPU.
"""

import sys
import time

from ..components import policy_index


def main() -> int:
    snapshot = policy_index.active_snapshot()
    print(f"Building index for snapshot {snapshot} with {policy_index.EMBED_MODEL} into {policy_index.INDEX_DIR}")
    started = time.perf_counter()
    try:
        count = policy_index.build()
    except policy_index.IndexUnavailableError as error:
        print(f"Failed: {error}")
        return 1
    print(f"Indexed {count} chunks in {time.perf_counter() - started:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
