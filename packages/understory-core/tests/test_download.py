"""Resilient download tests, all offline against a scripted loopback server.

Each test names the ASF failure it stands in for: a 5xx blip, a truncated body,
a server that ignores Range, a process killed mid-download, a credential
rejection that must *not* be retried. The point is to exercise the real
retry/resume/verify logic over genuine sockets, not a mock of it.
"""

from __future__ import annotations

import hashlib

import pytest
from understory_core.download import (
    DownloadError,
    RetryPolicy,
    download_file,
    get_with_retry,
)

# A policy with no real waiting, so the retry paths run instantly.
FAST = RetryPolicy(max_attempts=5, initial_backoff_s=0.0001, max_backoff_s=0.001, jitter=0.0)
NO_SLEEP = lambda _seconds: None  # noqa: E731


def _body(n: int = 4096) -> bytes:
    return bytes((i * 37 + 11) % 256 for i in range(n))


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()  # noqa: S324 (integrity, not security)


def test_transient_500_then_200_succeeds(http_server, tmp_path):
    http_server.body = _body()
    http_server.script = ["500"]  # first request fails, retry succeeds
    target = tmp_path / "g.h5"

    result = download_file(http_server.url, target, policy=FAST, sleep=NO_SLEEP)

    assert target.read_bytes() == http_server.body
    assert result.attempts == 2
    assert result.size_bytes == len(http_server.body)


def test_truncated_body_is_caught_then_recovered(http_server, tmp_path):
    """A body that stops short of its declared Content-Length must never be
    accepted as complete — the exact hole the old ``st_size > 0`` cache check
    left open. The client detects the short read and retries to a clean file."""
    http_server.body = _body()
    http_server.script = ["truncate"]  # sends half its declared length, then hangs up
    target = tmp_path / "g.h5"

    result = download_file(http_server.url, target, policy=FAST, sleep=NO_SLEEP)

    assert target.read_bytes() == http_server.body
    assert md5(target.read_bytes()) == md5(http_server.body)
    assert result.attempts == 2


def test_killed_process_partial_is_resumed_not_restarted(http_server, tmp_path):
    http_server.body = _body()
    target = tmp_path / "g.h5"
    # A .part left by a killed process: the first 1000 bytes are already on disk.
    partial = target.with_name(target.name + ".part")
    partial.write_bytes(http_server.body[:1000])

    result = download_file(http_server.url, target, policy=FAST, sleep=NO_SLEEP)

    assert target.read_bytes() == http_server.body
    assert result.resumed is True
    # Exactly one request, and it carried the resume offset.
    assert len(http_server.requests) == 1
    assert http_server.requests[0]["headers"].get("Range") == "bytes=1000-"


def test_server_ignoring_range_restarts_cleanly(http_server, tmp_path):
    http_server.body = _body()
    http_server.honor_range = False  # respond 200 to a ranged request
    target = tmp_path / "g.h5"
    partial = target.with_name(target.name + ".part")
    partial.write_bytes(b"\x00" * 1000)  # stale/garbage partial

    result = download_file(http_server.url, target, policy=FAST, sleep=NO_SLEEP)

    # The garbage prefix must be discarded, not appended to.
    assert target.read_bytes() == http_server.body
    assert result.resumed is False


def test_unauthorized_is_not_retried(http_server, tmp_path):
    http_server.body = _body()
    http_server.script = ["403", "403", "403"]
    target = tmp_path / "g.h5"

    with pytest.raises(PermissionError, match="Earthdata authorization"):
        download_file(http_server.url, target, policy=FAST, sleep=NO_SLEEP)

    # A single request — 403 means bad credentials, so retrying is pure delay.
    assert len(http_server.requests) == 1
    assert not target.exists()


def test_retry_after_header_sets_the_delay(http_server, tmp_path):
    http_server.body = _body()
    http_server.script = ["503-retry-after"]
    http_server.retry_after = "2"
    target = tmp_path / "g.h5"
    slept: list[float] = []

    result = download_file(http_server.url, target, policy=FAST, sleep=lambda s: slept.append(s))

    assert result.attempts == 2
    assert slept == [2.0]  # honoured Retry-After, not the computed backoff
    assert target.read_bytes() == http_server.body


def test_short_body_against_catalog_size_fails_after_budget(http_server, tmp_path):
    http_server.body = _body()
    target = tmp_path / "g.h5"
    policy = RetryPolicy(max_attempts=2, initial_backoff_s=0.0001, max_backoff_s=0.001, jitter=0.0)

    with pytest.raises(DownloadError, match="giving up"):
        download_file(
            http_server.url,
            target,
            expected_bytes=len(http_server.body) + 100,  # catalog says more than arrives
            policy=policy,
            sleep=NO_SLEEP,
        )
    assert not target.exists()


def test_correct_md5_is_verified_and_recorded(http_server, tmp_path):
    http_server.body = _body()
    target = tmp_path / "g.h5"

    result = download_file(
        http_server.url,
        target,
        expected_md5=md5(http_server.body),
        policy=FAST,
        sleep=NO_SLEEP,
    )

    assert result.checksum_verified is True
    assert result.md5 == md5(http_server.body)


def test_wrong_md5_is_rejected(http_server, tmp_path):
    http_server.body = _body()
    target = tmp_path / "g.h5"
    policy = RetryPolicy(max_attempts=2, initial_backoff_s=0.0001, max_backoff_s=0.001, jitter=0.0)

    with pytest.raises(DownloadError):
        download_file(
            http_server.url,
            target,
            expected_md5="0" * 32,
            policy=policy,
            sleep=NO_SLEEP,
        )
    assert not target.exists()


def test_no_checksum_records_digest_without_claiming_verification(http_server, tmp_path):
    """When ASF publishes no checksum, we record the bytes' own digest but say
    plainly it was not verified against the archive — an honest None-verified,
    not a fake True."""
    http_server.body = _body()
    target = tmp_path / "g.h5"

    result = download_file(http_server.url, target, policy=FAST, sleep=NO_SLEEP)

    assert result.md5 == md5(http_server.body)
    assert result.checksum_verified is False


def test_get_with_retry_recovers_from_5xx(http_server, tmp_path):
    http_server.body = b'{"ok": true}'
    http_server.script = ["500", "503-retry-after"]
    http_server.retry_after = "0"

    response = get_with_retry(http_server.url, policy=FAST, sleep=NO_SLEEP)

    assert response.json() == {"ok": True}
    assert len(http_server.requests) == 3


def test_lying_206_is_discarded_not_written_as_whole_file(http_server, tmp_path):
    """A 206 is a partial body by definition. One starting at the wrong offset
    used to be treated like a range-ignored 200 and written from byte zero,
    installing a fragment of the object as the 'complete' file — silently,
    whenever no catalog size or digest was available to catch it."""
    http_server.body = _body()
    http_server.script = ["lying-206"]  # then falls back to "ok"
    target = tmp_path / "g.h5"
    partial = target.with_name(target.name + ".part")
    partial.write_bytes(http_server.body[:1000])  # a genuine resumable prefix

    result = download_file(http_server.url, target, policy=FAST, sleep=NO_SLEEP)

    assert target.read_bytes() == http_server.body, "must never install a fragment"
    assert result.size_bytes == len(http_server.body)


def test_garbled_206_is_discarded_and_retried(http_server, tmp_path):
    http_server.body = _body()
    http_server.script = ["garbled-206"]
    target = tmp_path / "g.h5"
    target.with_name(target.name + ".part").write_bytes(http_server.body[:500])

    result = download_file(http_server.url, target, policy=FAST, sleep=NO_SLEEP)

    assert target.read_bytes() == http_server.body
    assert result.size_bytes == len(http_server.body)
