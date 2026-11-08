"""Answer feedback (thumbs up/down), recorded for human review by the team. Added 2026-11-07.

Feedback never changes answers: no pipeline module (graph, router, retrieval, topic cards, price
tool, synthesiser, verifier, model) imports this module, and feedback text is never put into a
prompt or retrieval query. It is untrusted input, so it is never logged at INFO or above.

Where it goes:
- LangSmith (primary review interface), as one feedback item (key "user_rating") per answer on its
  trace, when tracing gave the answer a run id and an API key is configured. A later click updates
  that item instead of adding another. Failures never fail the request.
- A local SQLite backup at data/feedback/feedback.db (git-ignored), one row per message_id.
  KOPI_FEEDBACK_DB overrides the path (tests use a temporary file).

There is deliberately no way to read feedback back over HTTP; see docs/feedback-loop.md.
"""

import logging
import os
import re
import sqlite3
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from langsmith import Client
from langsmith.utils import LangSmithConflictError, LangSmithNotFoundError, tracing_is_enabled
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator


logger = logging.getLogger(__name__)

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "feedback" / "feedback.db"
CONTEXT_SIZE = 1000
COMMENT_MAX = 500
# Never change this: it is what makes a message's LangSmith feedback id the same on every click.
FEEDBACK_ID_NAMESPACE = uuid.UUID("7c1e4f52-9a3b-4d86-b0f7-2e5a6c9d1f34")
_UUID = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
# C0/C1 control characters except newline, plus bidirectional overrides that can disguise text.
_CONTROL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f-\x9f‪-‮⁦-⁩]")

Reason = Literal[
    "wrong_numbers", "wrong_policy_info", "outdated", "misunderstood_question",
    "missing_info", "wrong_suggestions", "other",
]


class FeedbackRequest(BaseModel):
    """What the browser sends. Question, answer, route, snapshot and trace id are server-side only."""

    model_config = ConfigDict(extra="forbid")

    message_id: str = Field(pattern=_UUID)
    rating: StrictInt = Field(description="1 for thumbs up, -1 for thumbs down")
    reason: Reason | None = None
    comment: str | None = Field(default=None, max_length=COMMENT_MAX)

    @field_validator("rating")
    @classmethod
    def _plus_or_minus_one(cls, value: int) -> int:
        if value not in (1, -1):
            raise ValueError("rating must be 1 or -1")
        return value

    @field_validator("comment", mode="before")
    @classmethod
    def _clean_comment(cls, value):
        if not isinstance(value, str):
            return value
        value = _CONTROL.sub("", value).strip()
        return value or None


def feedback_id_for(message_id: str) -> str:
    """The LangSmith feedback id for an answer: one answer, one id, however many clicks."""
    return str(uuid.uuid5(FEEDBACK_ID_NAMESPACE, message_id))


def tracing_enabled() -> bool:
    """True when this process sends traces to LangSmith (so a run id will exist)."""
    try:
        return bool(tracing_is_enabled())
    except Exception:
        return False


@dataclass(frozen=True)
class AnswerContext:
    question: str
    answer: str
    route: str | None
    snapshot: str | None
    langsmith_run_id: str | None


class ContextStore:
    """The last CONTEXT_SIZE delivered answers, by message_id. In memory only; lost on restart."""

    def __init__(self, size: int = CONTEXT_SIZE):
        self.size, self._items, self._lock = size, OrderedDict(), threading.Lock()

    def remember(self, message_id: str, context: AnswerContext) -> None:
        with self._lock:
            self._items[message_id] = context
            self._items.move_to_end(message_id)
            while len(self._items) > self.size:
                self._items.popitem(last=False)

    def get(self, message_id: str) -> AnswerContext | None:
        with self._lock:
            return self._items.get(message_id)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback (
    message_id       TEXT PRIMARY KEY,
    langsmith_run_id TEXT,
    feedback_id      TEXT,
    rating           INTEGER NOT NULL CHECK (rating IN (1, -1)),
    reason           TEXT,
    comment          TEXT,
    question         TEXT,
    answer           TEXT,
    route            TEXT,
    snapshot         TEXT,
    context_missing  INTEGER NOT NULL,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
)
"""

# A later click overwrites the rating, reason and comment. Context is kept from the first row if
# the server has since forgotten it (for example after a restart).
_UPSERT = """
INSERT INTO feedback (message_id, langsmith_run_id, feedback_id, rating, reason, comment, question, answer,
                      route, snapshot, context_missing, created_at, updated_at)
VALUES (:message_id, :langsmith_run_id, :feedback_id, :rating, :reason, :comment, :question, :answer,
        :route, :snapshot, :context_missing, :now, :now)
ON CONFLICT(message_id) DO UPDATE SET
    langsmith_run_id = COALESCE(excluded.langsmith_run_id, feedback.langsmith_run_id),
    feedback_id = excluded.feedback_id,
    rating = excluded.rating,
    reason = excluded.reason,
    comment = excluded.comment,
    question = COALESCE(feedback.question, excluded.question),
    answer = COALESCE(feedback.answer, excluded.answer),
    route = COALESCE(feedback.route, excluded.route),
    snapshot = COALESCE(feedback.snapshot, excluded.snapshot),
    context_missing = MIN(feedback.context_missing, excluded.context_missing),
    updated_at = excluded.updated_at
"""


def db_path() -> Path:
    return Path(os.getenv("KOPI_FEEDBACK_DB") or DEFAULT_DB)


class FeedbackStore:
    """Local SQLite backup, created on first use."""

    def __init__(self, path: Path | None = None):
        self._path, self._lock = path, threading.Lock()

    @property
    def path(self) -> Path:
        return self._path or db_path()

    def save(self, item: FeedbackRequest, context: AnswerContext | None) -> bool:
        """Store the rating. Returns True if this is the first one for this message_id."""
        row = {
            "message_id": item.message_id,
            "langsmith_run_id": context.langsmith_run_id if context else None,
            "feedback_id": feedback_id_for(item.message_id),
            "rating": item.rating,
            "reason": item.reason,
            "comment": item.comment,
            "question": context.question if context else None,
            "answer": context.answer if context else None,
            "route": context.route if context else None,
            "snapshot": context.snapshot if context else None,
            "context_missing": 0 if context else 1,
            "now": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        path = self.path
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path)
            try:
                with connection:
                    connection.execute(_SCHEMA)
                    columns = {column[1] for column in connection.execute("PRAGMA table_info(feedback)")}
                    if "feedback_id" not in columns:  # database created before this column existed
                        connection.execute("ALTER TABLE feedback ADD COLUMN feedback_id TEXT")
                    first = connection.execute("SELECT 1 FROM feedback WHERE message_id = ?",
                                               (item.message_id,)).fetchone() is None
                    connection.execute(_UPSERT, row)
            finally:
                connection.close()
        logger.debug("Feedback stored for message %s", item.message_id)
        return first


def langsmith_comment(reason: str | None, comment: str | None) -> str | None:
    if reason and comment:
        return f"{reason}: {comment}"
    return reason or comment


def send_to_langsmith(run_id: str | None, message_id: str, rating: int, reason: str | None,
                      comment: str | None, first: bool) -> bool:
    """Create or update this answer's one feedback item. Never raises; never logs the key or text."""
    if not run_id or not (os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")):
        return False
    feedback_id = feedback_id_for(message_id)
    score = 1 if rating == 1 else 0
    text = langsmith_comment(reason, comment)
    try:
        client = Client()

        def update() -> None:
            # "" clears the old text: the SDK skips comment=None, which would leave a 👎 reason on a 👍.
            client.update_feedback(feedback_id, score=score, comment=text or "")

        def create_or_update() -> None:
            try:
                client.create_feedback(
                    run_id,
                    key="user_rating",
                    score=score,
                    comment=text,
                    feedback_id=feedback_id,
                    stop_after_attempt=2,
                    # Feedback should not change how long LangSmith keeps the trace.
                    extend_trace_retention=False,
                )
            except LangSmithConflictError:  # another click created it first
                update()

        if first:
            create_or_update()
        else:
            try:
                update()
            except LangSmithNotFoundError:  # the earlier create failed or has not landed yet
                create_or_update()
        return True
    except Exception as error:
        logger.warning("LangSmith feedback was not sent (%s).", type(error).__name__)
        return False
