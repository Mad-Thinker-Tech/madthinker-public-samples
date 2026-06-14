"""Shared test doubles for the HTTP boundary.

The real client talks to a live endpoint, but every unit test mocks the
transport so the suite runs with no API key and no network.
"""

import requests


class FakeResponse:
    """Minimal stand-in for ``requests.Response``.

    ``content`` carries the raw bytes used when standing in for a photo
    download; it defaults to empty for the JSON export responses.
    """

    def __init__(self, status_code, payload=None, content=b""):
        self.status_code = status_code
        self._payload = payload
        self.content = content

    def json(self):
        return self._payload


class FakeSession:
    """Replays scripted responses for ``.get()``.

    The export endpoint is served from ``scripted`` (a list consumed in
    order); each item is either a :class:`FakeResponse` (or any object with
    ``status_code`` and ``json()``) or an ``Exception`` instance, which is
    raised to simulate a connection failure.

    Photo downloads are served from ``photos``, a ``{url: response-or-exception}``
    map keyed by the signed URL, so a row's image fetch does not consume an
    export response. Every call is recorded in ``self.calls``.
    """

    def __init__(self, scripted, photos=None):
        self._scripted = list(scripted)
        self.photos = photos or {}
        self.calls = []

    def get(self, url, *, headers=None, params=None, timeout=None):
        self.calls.append(
            {"url": url, "headers": headers, "params": params, "timeout": timeout}
        )
        if url in self.photos:
            item = self.photos[url]
        else:
            item = self._scripted.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def conn_error(message="boom"):
    return requests.exceptions.ConnectionError(message)
