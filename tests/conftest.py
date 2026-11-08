"""Keep test runs out of LangSmith. load_dotenv() never overrides these."""

import os

os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

# Feedback tests must never touch the real data/feedback/feedback.db.
import tempfile  # noqa: E402

os.environ["KOPI_FEEDBACK_DB"] = os.path.join(tempfile.mkdtemp(prefix="kopi-feedback-"), "feedback.db")
