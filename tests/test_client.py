"""Tests for the export HTTP client: request shaping, error mapping, retries."""

import pytest

from madthinker_export.client import (
    AuthError,
    BadRequestError,
    ExportClient,
    RateLimitError,
    ServerError,
)
from tests.conftest import FakeResponse, FakeSession, conn_error

URL = "https://example.supabase.co/functions/v1/tca-catch-reports-export"
KEY = "secret-key"

OK_PAGE = {"rows": [], "next_cursor": "c1", "has_more": False, "returned_count": 0}


def make_client(scripted, **kwargs):
    """Build a client wired to a scripted session with no real sleeping."""
    session = FakeSession(scripted)
    client = ExportClient(
        URL,
        KEY,
        session=session,
        sleep=lambda _seconds: None,
        **kwargs,
    )
    return client, session


# -- request shaping ------------------------------------------------------
def test_first_run_sends_since_and_api_key_header():
    client, session = make_client([FakeResponse(200, OK_PAGE)])
    client.fetch(since="1970-01-01T00:00:00Z")
    call = session.calls[0]
    assert call["url"] == URL
    assert call["headers"]["x-tca-api-key"] == KEY
    assert call["params"]["since"] == "1970-01-01T00:00:00Z"
    assert "cursor" not in call["params"]


def test_cursor_call_sends_cursor_not_since():
    client, session = make_client([FakeResponse(200, OK_PAGE)])
    client.fetch(cursor="saved-cursor")
    call = session.calls[0]
    assert call["params"]["cursor"] == "saved-cursor"
    assert "since" not in call["params"]


def test_default_limit_is_1000():
    client, session = make_client([FakeResponse(200, OK_PAGE)])
    client.fetch(since="1970-01-01T00:00:00Z")
    assert session.calls[0]["params"]["limit"] == 1000


def test_returns_parsed_payload():
    page = {"rows": [{"id": "a"}], "next_cursor": "c2", "has_more": True, "returned_count": 1}
    client, _ = make_client([FakeResponse(200, page)])
    assert client.fetch(cursor="x") == page


# -- non-retryable errors -------------------------------------------------
def test_401_raises_auth_error_without_retry():
    client, session = make_client(
        [FakeResponse(401, {"error": "Unauthorized"})]
    )
    with pytest.raises(AuthError):
        client.fetch(cursor="x")
    assert len(session.calls) == 1


def test_400_raises_bad_request_with_message_no_retry():
    client, session = make_client(
        [FakeResponse(400, {"error": "Invalid cursor."})]
    )
    with pytest.raises(BadRequestError) as exc:
        client.fetch(cursor="bad")
    assert "Invalid cursor." in str(exc.value)
    assert len(session.calls) == 1


# -- retryable errors -----------------------------------------------------
def test_429_retries_then_succeeds():
    client, session = make_client(
        [FakeResponse(429, {"error": "Rate limit exceeded"}), FakeResponse(200, OK_PAGE)]
    )
    assert client.fetch(cursor="x") == OK_PAGE
    assert len(session.calls) == 2


def test_500_retries_then_succeeds():
    client, session = make_client(
        [FakeResponse(500, {"error": "Internal server error"}), FakeResponse(200, OK_PAGE)]
    )
    assert client.fetch(cursor="x") == OK_PAGE
    assert len(session.calls) == 2


def test_connection_error_retries_then_succeeds():
    client, session = make_client([conn_error(), FakeResponse(200, OK_PAGE)])
    assert client.fetch(cursor="x") == OK_PAGE
    assert len(session.calls) == 2


def test_server_error_retry_exhaustion_raises_last_error():
    client, session = make_client(
        [FakeResponse(500, {"error": "Internal server error"})] * 9,
        max_retries=4,
    )
    with pytest.raises(ServerError):
        client.fetch(cursor="x")
    # 1 initial attempt + 4 retries = 5 calls
    assert len(session.calls) == 5


def test_rate_limit_exhaustion_raises_rate_limit_error():
    client, _ = make_client(
        [FakeResponse(429, {"error": "Rate limit exceeded"})] * 9,
        max_retries=2,
    )
    with pytest.raises(RateLimitError):
        client.fetch(cursor="x")
