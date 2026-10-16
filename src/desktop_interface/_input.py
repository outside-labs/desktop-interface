"""Shared validation and best-effort cleanup for explicitly submitted input."""

from threading import Event
import time

from .errors import InputCancelledError
from .geometry import _finite


def duration(value, name="duration"):
    value = _finite(value, name)
    if not 0 <= value <= 30:
        raise ValueError(f"{name} must be between zero and 30 seconds")
    return value


def cancellation(value):
    if value is not None and not isinstance(value, Event):
        raise TypeError("cancel must be a threading.Event or None")
    return value


def pause(seconds, cancel):
    if cancel is not None:
        if cancel.wait(seconds):
            raise InputCancelledError("Input operation was cancelled")
    elif seconds:
        time.sleep(seconds)


def cleanup(actions):
    failures = []
    for action in actions:
        try:
            action()
        except BaseException as error:
            failures.append(error)
    if failures:
        raise BaseExceptionGroup("Input cleanup failed", failures)
