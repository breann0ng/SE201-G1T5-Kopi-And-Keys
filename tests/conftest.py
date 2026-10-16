"""Keep test runs out of LangSmith. load_dotenv() never overrides these."""

import os

os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"
