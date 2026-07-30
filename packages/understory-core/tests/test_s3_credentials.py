"""S3 credential provider tests, offline against the scripted server.

The behaviour that matters is refresh-before-expiry: a run longer than the
one-hour credential lifetime must not die at the hour mark. The clock is
injected so a test can jump past expiry without waiting.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from understory_core.download import RetryPolicy
from understory_core.s3_credentials import S3CredentialProvider, S3Credentials

FAST = RetryPolicy(max_attempts=3, initial_backoff_s=0.0001, max_backoff_s=0.001, jitter=0.0)


def _payload(token: str, expiration: datetime) -> bytes:
    return json.dumps(
        {
            "accessKeyId": "AKIA-test",
            "secretAccessKey": "secret",
            "sessionToken": token,
            "expiration": expiration.isoformat(),
        }
    ).encode()


def test_parses_and_exposes_boto3_kwargs():
    creds = S3Credentials.from_payload(
        {
            "accessKeyId": "AKIA",
            "secretAccessKey": "shhh",
            "sessionToken": "tok",
            "expiration": "2026-07-21 12:00:00+00:00",
        }
    )
    kwargs = creds.as_boto3_kwargs()
    assert kwargs["aws_session_token"] == "tok"
    assert kwargs["region_name"] == "us-west-2"


def test_naive_expiration_is_read_as_utc():
    creds = S3Credentials.from_payload(
        {
            "accessKeyId": "a",
            "secretAccessKey": "b",
            "sessionToken": "c",
            "expiration": "2026-07-21T12:00:00",
        }
    )
    assert creds.expiration.tzinfo is not None


def test_credentials_are_cached_until_near_expiry(http_server):
    now = datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC)
    http_server.body = _payload("token-1", now + timedelta(hours=1))
    provider = S3CredentialProvider(url=http_server.url, now=lambda: now, policy=FAST)

    first = provider.credentials()
    second = provider.credentials()

    assert first.session_token == "token-1"
    assert second.session_token == "token-1"
    assert len(http_server.requests) == 1  # served from cache, no re-fetch


def test_credentials_refresh_before_they_expire(http_server):
    clock = {"t": datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC)}
    http_server.body = _payload("token-1", clock["t"] + timedelta(hours=1))
    provider = S3CredentialProvider(url=http_server.url, now=lambda: clock["t"], policy=FAST)

    first = provider.credentials()
    assert first.session_token == "token-1"

    # Jump to 58 minutes in — inside the 5-minute refresh margin of the
    # one-hour credential, which is the moment a naive run would fail.
    clock["t"] += timedelta(minutes=58)
    http_server.body = _payload("token-2", clock["t"] + timedelta(hours=1))
    second = provider.credentials()

    assert second.session_token == "token-2"
    assert len(http_server.requests) == 2  # actually re-fetched


def test_provider_retries_a_transient_error(http_server):
    now = datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC)
    http_server.body = _payload("token-1", now + timedelta(hours=1))
    http_server.script = ["500"]  # first fetch blips, retry succeeds
    provider = S3CredentialProvider(url=http_server.url, now=lambda: now, policy=FAST, session=None)
    # The default sleep is real, but FAST's backoff is sub-millisecond.
    creds = provider.credentials()
    assert creds.session_token == "token-1"
    assert len(http_server.requests) == 2


def test_already_expired_fresh_credential_is_refused_not_returned(http_server):
    """A stale credential from the endpoint (clock skew, cached upstream) used
    to be cached and handed out, driving callers into a 403 -> invalidate ->
    identical re-fetch loop with no visible cause."""
    import pytest

    now = datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC)
    http_server.body = _payload("token-stale", now - timedelta(hours=1))
    provider = S3CredentialProvider(url=http_server.url, now=lambda: now, policy=FAST)

    with pytest.raises(RuntimeError, match="already inside the .* refresh margin"):
        provider.credentials()
    # And it is not cached: the next call re-fetches rather than serving it.
    http_server.body = _payload("token-good", now + timedelta(hours=1))
    assert provider.credentials().session_token == "token-good"
