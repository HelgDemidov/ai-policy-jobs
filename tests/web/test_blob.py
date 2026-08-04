"""Tests for web/api/_blob.py. requests_mock intercepts everything — no real
network call, no real Vercel Blob store touched."""
import _blob
import pytest
import requests


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "test-token")


def test_download_hits_store_url_with_bearer_auth(requests_mock):
    requests_mock.get(
        "https://tzxwwo2y42v4il6x.private.blob.vercel-storage.com/jobs.db",
        content=b"db-bytes",
    )

    result = _blob.download()

    assert result == b"db-bytes"
    assert requests_mock.last_request.headers["Authorization"] == "Bearer test-token"


def test_download_with_etag_returns_content_and_etag(requests_mock):
    requests_mock.get(
        "https://tzxwwo2y42v4il6x.private.blob.vercel-storage.com/jobs.db",
        content=b"db-bytes",
        headers={"etag": '"abc123"'},
    )

    content, etag = _blob.download_with_etag()

    assert content == b"db-bytes"
    assert etag == '"abc123"'


def test_upload_sends_correct_headers_and_pathname(requests_mock):
    requests_mock.put("https://vercel.com/api/blob", json={"pathname": "jobs.db"})

    _blob.upload(b"new-bytes", if_match='"abc123"')

    req = requests_mock.last_request
    assert req.qs.get("pathname") == ["jobs.db"]
    assert req.headers["Authorization"] == "Bearer test-token"
    assert req.headers["x-api-version"] == "12"
    assert req.headers["x-vercel-blob-access"] == "private"
    assert req.headers["x-allow-overwrite"] == "1"
    assert req.headers["x-if-match"] == '"abc123"'
    assert req.body == b"new-bytes"


def test_upload_raises_on_precondition_failed(requests_mock):
    requests_mock.put(
        "https://vercel.com/api/blob",
        status_code=412,
        json={"error": {"code": "precondition_failed"}},
    )

    with pytest.raises(requests.HTTPError):
        _blob.upload(b"new-bytes", if_match='"stale-etag"')


def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="BLOB_READ_WRITE_TOKEN"):
        _blob.download()
