"""Resilient HTTP retrieval of large NISAR granules.

A benchmark build pulls thousands of ~1.9 GB HDF5 files over hours. At that
duration every transient failure ASF can produce will happen at least once, so
this path is built to survive them rather than abort the build:

- **Retry with exponential backoff and jitter** on connection errors, timeouts,
  429 and 5xx. ``Retry-After`` wins over the computed backoff when present.
  401/403 are *not* retried — they mean the Earthdata credentials are wrong, and
  retrying only delays a clear error by a minute.
- **Resume** via HTTP Range, so a connection dropped at 1.8 GB costs the last
  100 MB rather than the whole granule. Whether the server honoured the range is
  read off the response (206 plus a matching ``Content-Range``), never assumed;
  a 200 to a ranged request means the range was ignored and the file restarts
  from byte zero.
- **Length verification** against ``Content-Length`` (plus the catalog size when
  the caller has one). A body that stops short of its declared length is the
  failure the old ``st_size > 0`` cache check could not see.

Authentication is NASA Earthdata via ``~/.netrc`` (docs/DATA_ACCESS.md);
requests follows the URS redirect dance natively, and nothing here touches
temporary S3 credentials — those belong to the separate in-region path in
``understory_core.s3_credentials``.
"""

from __future__ import annotations

import email.utils
import hashlib
import logging
import os
import random
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import requests
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Transport-level failures that are worth another attempt: the request never
# reached a healthy server, or the server said "not now".
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

# Credential failures. Retrying these is pure delay: the netrc entry is missing,
# wrong, or the Earthdata account has not accepted the ASF EULA.
UNAUTHORIZED_STATUS = frozenset({401, 403})

CHUNK_BYTES = 1 << 20
_HASH_BLOCK_BYTES = 1 << 20


class DownloadError(RuntimeError):
    """A download failed after exhausting its retry budget."""


class IntegrityError(DownloadError):
    """Bytes landed, but they are not the object that was asked for."""


class RetryPolicy(BaseModel):
    """How hard to try, and how long to wait between tries.

    Defaults are sized for ASF: five attempts spanning about a minute of
    backoff, a read timeout generous enough for a slow but live transfer of a
    1 GB-scale body, and a cap on how long a server's ``Retry-After`` may park
    the build.
    """

    max_attempts: int = Field(default=5, ge=1)
    initial_backoff_s: float = Field(default=1.0, gt=0)
    max_backoff_s: float = Field(default=60.0, gt=0)
    multiplier: float = Field(default=2.0, ge=1.0)
    jitter: float = Field(default=0.25, ge=0.0, le=1.0)
    connect_timeout_s: float = Field(default=30.0, gt=0)
    read_timeout_s: float = Field(default=300.0, gt=0)
    max_retry_after_s: float = Field(default=300.0, gt=0)

    model_config = {"frozen": True}

    @property
    def timeout(self) -> tuple[float, float]:
        """(connect, read) timeout for requests.

        There is deliberately no timeout on the *whole* transfer: a 1.9 GB body
        on a slow link is not a hung request, and a wall-clock cap would abort
        healthy downloads. The read timeout is what catches a stalled socket.
        """
        return (self.connect_timeout_s, self.read_timeout_s)

    def backoff_seconds(self, attempt: int, retry_after: float | None = None) -> float:
        """Delay before retrying, ``attempt`` being the 1-based try that failed.

        Jitter is multiplicative and symmetric: enough to stop a pool of workers
        rebounding off ASF in lockstep, not so much that the cap stops meaning
        anything.
        """
        if retry_after is not None:
            return min(max(retry_after, 0.0), self.max_retry_after_s)
        delay = self.initial_backoff_s * self.multiplier ** (attempt - 1)
        delay = min(delay, self.max_backoff_s)
        return delay * random.uniform(1.0 - self.jitter, 1.0 + self.jitter)


DEFAULT_RETRY_POLICY = RetryPolicy()


class DownloadResult(BaseModel):
    """What actually landed on disk, for the manifest to record."""

    path: Path
    size_bytes: int
    md5: str | None = None
    #: True only when the caller supplied an expected digest and it matched.
    #: A locally computed ``md5`` with this False is a fingerprint of the bytes
    #: we received, not evidence that they are the bytes ASF holds.
    checksum_verified: bool = False
    attempts: int = 1
    resumed: bool = False

    model_config = {"frozen": True}


class _TransientError(Exception):
    """Internal: this attempt failed in a way worth retrying."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def download_file(
    url: str,
    target: Path | str,
    *,
    expected_bytes: int | None = None,
    expected_md5: str | None = None,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    session: requests.Session | None = None,
    sleep: Callable[[float], None] = time.sleep,
    compute_md5: bool = True,
) -> DownloadResult:
    """Download ``url`` to ``target``, retrying and resuming as needed.

    Bytes accumulate in ``<target>.part`` and are renamed into place only once
    every check passes, so ``target`` existing always means a complete transfer
    — and a killed process leaves a ``.part`` that the next call resumes rather
    than a short file that looks finished.

    ``expected_bytes`` and ``expected_md5`` come from the granule catalog when
    it carries them (see ``discovery.pair_from_asf_properties``); both are
    optional and each is checked independently of the server's own headers.
    """
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")

    owns_session = session is None
    session = session or requests.Session()
    resumed = False
    last_failure = ""
    digest: str | None = None
    try:
        for attempt in range(1, policy.max_attempts + 1):
            try:
                resumed |= _attempt(session, url, partial, policy, expected_bytes)
                digest = _file_md5(partial) if (compute_md5 or expected_md5 is not None) else None
                if expected_md5 is not None and digest != expected_md5:
                    partial.unlink(missing_ok=True)
                    raise _TransientError(
                        f"md5 mismatch: got {digest}, catalog says {expected_md5}"
                    )
            except _TransientError as failure:
                last_failure = str(failure)
                if attempt == policy.max_attempts:
                    break
                delay = policy.backoff_seconds(attempt, failure.retry_after)
                logger.warning(
                    "%s: attempt %d/%d failed (%s); retrying in %.1fs",
                    url,
                    attempt,
                    policy.max_attempts,
                    failure,
                    delay,
                )
                sleep(delay)
                continue

            size = partial.stat().st_size
            partial.replace(target)
            return DownloadResult(
                path=target,
                size_bytes=size,
                md5=digest,
                checksum_verified=expected_md5 is not None,
                attempts=attempt,
                resumed=resumed,
            )
    finally:
        if owns_session:
            session.close()

    raise DownloadError(
        f"giving up on {url} after {policy.max_attempts} attempts; last failure: {last_failure}"
    )


def get_with_retry(
    url: str,
    *,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    session: requests.Session | None = None,
    sleep: Callable[[float], None] = time.sleep,
    **kwargs,
) -> requests.Response:
    """A plain GET with the same retry classification as ``download_file``.

    For small responses (the S3 credentials endpoint), where resume and length
    checks are meaningless but a 503 during a long run is not.
    """
    owns_session = session is None
    session = session or requests.Session()
    last_failure = ""
    try:
        for attempt in range(1, policy.max_attempts + 1):
            try:
                try:
                    response = session.get(url, timeout=policy.timeout, **kwargs)
                except requests.RequestException as exc:
                    raise _TransientError(f"{type(exc).__name__}: {exc}") from exc
                _reject_unauthorized(response, url)
                if response.status_code in RETRYABLE_STATUS:
                    raise _TransientError(
                        f"HTTP {response.status_code}", _retry_after_seconds(response, policy)
                    )
                response.raise_for_status()
                return response
            except _TransientError as failure:
                last_failure = str(failure)
                if attempt == policy.max_attempts:
                    break
                delay = policy.backoff_seconds(attempt, failure.retry_after)
                logger.warning(
                    "%s: attempt %d failed (%s); retrying in %.1fs", url, attempt, failure, delay
                )
                sleep(delay)
    finally:
        if owns_session:
            session.close()
    raise DownloadError(
        f"giving up on {url} after {policy.max_attempts} attempts; last failure: {last_failure}"
    )


def _attempt(
    session: requests.Session,
    url: str,
    partial: Path,
    policy: RetryPolicy,
    expected_bytes: int | None,
) -> bool:
    """One request/write cycle into ``partial``. Returns whether it resumed.

    Raises ``_TransientError`` for anything the caller should try again, and lets
    permanent failures (401/403, 404, a bad URL) propagate untouched.
    """
    resume_from = partial.stat().st_size if partial.exists() else 0
    headers = {"Range": f"bytes={resume_from}-"} if resume_from else {}

    try:
        response = session.get(url, headers=headers, stream=True, timeout=policy.timeout)
    except requests.RequestException as exc:
        raise _TransientError(f"{type(exc).__name__}: {exc}") from exc

    with response:
        _reject_unauthorized(response, url)
        if response.status_code == 416:
            # The partial file is at least as long as the object — it cannot be
            # what we want, and it cannot be resumed. Start over.
            partial.unlink(missing_ok=True)
            raise _TransientError("server rejected the resume range (416); restarting from zero")
        if response.status_code in RETRYABLE_STATUS:
            raise _TransientError(
                f"HTTP {response.status_code}", _retry_after_seconds(response, policy)
            )
        response.raise_for_status()

        resumed = False
        mode = "wb"
        if resume_from:
            if response.status_code == 206:
                if _range_start(response) == resume_from:
                    mode, resumed = "ab", True
                else:
                    # A 206 is by definition a partial body. One that starts
                    # anywhere but where we asked answers a different question,
                    # and writing it from byte zero would install a fragment of
                    # the object as the "complete" file — the corruption is
                    # silent whenever no catalog size or digest is available to
                    # catch it. Protocol violation: discard and retry clean.
                    partial.unlink(missing_ok=True)
                    raise _TransientError(
                        f"206 Content-Range starts at {_range_start(response)!r}, "
                        f"not the requested {resume_from}; discarding partial and retrying"
                    )
            else:
                logger.info(
                    "%s: server did not honour Range (HTTP %d, Accept-Ranges: %s); "
                    "restarting the %d bytes already fetched",
                    url,
                    response.status_code,
                    response.headers.get("Accept-Ranges", "<absent>"),
                    resume_from,
                )
                resume_from = 0

        declared = _content_length(response)
        try:
            with open(partial, mode) as handle:
                for chunk in response.iter_content(chunk_size=CHUNK_BYTES):
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
        except requests.RequestException as exc:
            # A dropped connection mid-body. Whatever was written stays, and the
            # next attempt resumes from it.
            raise _TransientError(f"{type(exc).__name__}: {exc}") from exc

    size = partial.stat().st_size
    _check_length(
        partial, size, "Content-Length", None if declared is None else resume_from + declared
    )
    _check_length(partial, size, "catalog size", expected_bytes)
    return resumed


def _check_length(partial: Path, size: int, source: str, expected: int | None) -> None:
    if expected is None or size == expected:
        return
    if size < expected:
        # Resumable: keep the bytes, ask for the rest.
        raise _TransientError(f"short read: {size} of {expected} bytes ({source})")
    partial.unlink(missing_ok=True)
    raise _TransientError(f"over-long response: {size} bytes against {expected} ({source})")


def _reject_unauthorized(response: requests.Response, url: str) -> None:
    if response.status_code in UNAUTHORIZED_STATUS:
        raise PermissionError(
            f"Earthdata authorization failed for {url} (HTTP {response.status_code}) — put "
            "NASA Earthdata credentials in ~/.netrc (machine urs.earthdata.nasa.gov ...) and "
            "accept the ASF EULA; see docs/DATA_ACCESS.md. Not retried: retrying a "
            "credential failure only delays the error."
        )


def _content_length(response: requests.Response) -> int | None:
    """Body length of *this* response, or None when the server does not say.

    Absent for chunked transfer encoding, in which case length verification is
    simply unavailable and the structural HDF5 check in ``ingest`` is the only
    truncation guard left.
    """
    raw = response.headers.get("Content-Length")
    if raw is None or response.headers.get("Transfer-Encoding", "").lower() == "chunked":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _range_start(response: requests.Response) -> int | None:
    """The start offset a 206's ``Content-Range`` claims, or None if unparseable.

    The caller compares this against the offset it requested. A 200 never gets
    here (it means the Range header was ignored and the whole object follows,
    which restarts cleanly); a 206 starting anywhere but the requested offset is
    a partial body masquerading as a resume and must be discarded, never written.
    """
    content_range = response.headers.get("Content-Range", "")
    # "bytes 1024-2047/2048"
    try:
        return int(content_range.split()[1].split("-")[0])
    except (IndexError, ValueError):
        return None


def _retry_after_seconds(response: requests.Response, policy: RetryPolicy) -> float | None:
    """``Retry-After`` in seconds, accepting both the delta and HTTP-date forms."""
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return min(float(raw), policy.max_retry_after_s)
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max((when - datetime.now(UTC)).total_seconds(), 0.0)


def _file_md5(path: Path) -> str:
    """MD5 of a file on disk, read in blocks.

    Computed over the finished file rather than streamed during the write,
    because a resumed download never sees its own first bytes.
    """
    digest = hashlib.md5()  # noqa: S324 — integrity check against ASF, not a security boundary
    with open(path, "rb") as handle:
        while block := handle.read(_HASH_BLOCK_BYTES):
            digest.update(block)
    return digest.hexdigest()
