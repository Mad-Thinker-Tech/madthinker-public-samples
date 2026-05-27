"""Shared test doubles for the HTTP boundary.

The real client talks to a live endpoint, but every unit test mocks the
transport so the suite runs with no API key and no network.
"""

import requests


class FakeResponse:
    """Minimal stand-in for ``requests.Response``."""

    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    """Replays a scripted list of responses / exceptions for ``.get()``.

    Each scripted item is either a :class:`FakeResponse` (or any object with
    ``status_code`` and ``json()``) or an ``Exception`` instance, which is
    raised to simulate a connection failure. Every call is recorded in
    ``self.calls`` as the kwargs passed to ``get``.
    """

    def __init__(self, scripted):
        self._scripted = list(scripted)
        self.calls = []

    def get(self, url, *, headers=None, params=None, timeout=None):
        self.calls.append(
            {"url": url, "headers": headers, "params": params, "timeout": timeout}
        )
        item = self._scripted.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def conn_error(message="boom"):
    return requests.exceptions.ConnectionError(message)
