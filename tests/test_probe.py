"""Tests for the endpoint probe.

The probe answers one question: *is this URL the correct, live export
endpoint?* It does so with a static check (URL vs the canonical value) and a
single live GET whose status localises the fault. Every test mocks the
transport, so the suite still runs with no key and no network.
"""

from madthinker_export.probe import CANONICAL, probe, static_diff
from tests.conftest import FakeResponse, FakeSession, conn_error

# The stale "old Lovable" URL a customer hit: wrong host AND missing the tca- path.
WRONG = "https://koyegehcwcrvxpfthkxq.supabase.co/functions/v1/catch-reports-export"


def ok_page(count=0):
    rows = [{"id": f"r{i}", "deleted_at": None} for i in range(count)]
    return FakeResponse(
        200, {"rows": rows, "next_cursor": "c", "has_more": False, "returned_count": count}
    )


def test_static_diff_flags_host_and_path():
    notes = " ".join(static_diff(WRONG))
    assert "host" in notes
    assert "path" in notes


def test_static_diff_clean_for_canonical_ignoring_query_and_slash():
    assert static_diff(CANONICAL) == []
    assert static_diff(CANONICAL + "?since=1970-01-01T00:00:00Z") == []
    assert static_diff(CANONICAL + "/") == []


def test_probe_fully_validates_on_200_with_contract_shape():
    result = probe(CANONICAL, "tca_live_key", session=FakeSession([ok_page(3)]))
    assert result.ok
    assert "FULLY VALIDATED" in result.verdict


def test_probe_flags_wrong_url_statically_and_live():
    session = FakeSession([FakeResponse(404, {"message": "no"})])
    result = probe(WRONG, "tca_live_key", session=session)
    assert not result.ok
    assert "STATIC CHECK: FAIL" in result.verdict
    assert "URL WRONG" in result.verdict


def test_probe_404_on_canonical_is_url_wrong():
    session = FakeSession([FakeResponse(404, {"message": "Requested function was not found"})])
    result = probe(CANONICAL, "k", session=session)
    assert not result.ok
    assert "URL WRONG" in result.verdict


def test_probe_401_means_url_right_key_wrong_and_tolerates_missing_key():
    session = FakeSession([FakeResponse(401, {"error": "Unauthorized"})])
    result = probe(CANONICAL, None, session=session)
    assert not result.ok
    assert "URL RIGHT, KEY WRONG" in result.verdict


def test_probe_400_means_url_right():
    session = FakeSession([FakeResponse(400, {"error": "Invalid cursor."})])
    result = probe(CANONICAL, "k", session=session)
    assert not result.ok
    assert "URL RIGHT" in result.verdict


def test_probe_network_error_is_reported():
    result = probe(CANONICAL, "k", session=FakeSession([conn_error("dns failure")]))
    assert not result.ok
    assert "NETWORK ERROR" in result.verdict


def test_probe_200_with_wrong_shape_is_not_validated():
    result = probe(CANONICAL, "k", session=FakeSession([FakeResponse(200, {"unexpected": True})]))
    assert not result.ok
    assert "does not match the contract" in result.verdict
