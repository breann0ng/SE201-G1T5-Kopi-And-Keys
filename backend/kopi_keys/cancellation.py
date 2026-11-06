"""Cancellation shared by one streamed request and its model calls."""

from contextvars import ContextVar
from threading import Event

request_cancelled: ContextVar[Event | None] = ContextVar("kopi_request_cancelled", default=None)
