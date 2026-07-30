"""ASF's temporary S3 credentials, kept fresh across a long run.

The in-region path reads granules straight out of
``s3://sds-n-cumulus-prod-nisar-products/...`` from ``us-west-2``. That needs
temporary credentials minted by ASF's Earthdata-authenticated endpoint, and
**they expire after about an hour** — so any build longer than one hour that
fetches them once dies partway through, which is exactly the failure this module
exists to prevent. ``S3CredentialProvider.credentials()`` re-fetches shortly
before expiry, so callers can simply ask on every object.

Reference: https://nisar-docs.asf.alaska.edu/aws-s3-access/

Three properties of these credentials are worth stating because they bound what
can go wrong: they work **only from us-west-2**, they grant **only ListBucket
and GetObject**, and obtaining them requires the same Earthdata login as HTTPS.

**The HTTPS path does not use any of this.** ``download.download_file`` and
``ingest.fetch_granule`` authenticate with ``~/.netrc`` against
``urs.earthdata.nasa.gov`` and never mint an S3 credential; there is nothing in
that path that expires mid-run. Nothing in the repository consumes this module
yet — the S3 reader itself is unwritten (it needs boto3, which is not a
dependency), and ``as_boto3_kwargs`` is the seam it will plug into.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import requests
from pydantic import BaseModel

from understory_core.download import DEFAULT_RETRY_POLICY, RetryPolicy, get_with_retry

logger = logging.getLogger(__name__)

NISAR_S3_CREDENTIALS_URL = "https://nisar.asf.earthdatacloud.nasa.gov/s3credentials"

#: The bucket is readable from this region only; from anywhere else the
#: credentials authenticate fine and every GET fails.
S3_REGION = "us-west-2"

#: Refresh this long before the stated expiry. Wide enough to cover a slow
#: refresh and clock skew between us and ASF, narrow enough not to churn.
DEFAULT_REFRESH_MARGIN = timedelta(minutes=5)


class S3Credentials(BaseModel):
    """One set of temporary AWS credentials from ASF."""

    access_key_id: str
    secret_access_key: str
    session_token: str
    expiration: datetime

    model_config = {"frozen": True}

    @classmethod
    def from_payload(cls, payload: dict) -> S3Credentials:
        """Parse the endpoint's JSON response."""
        try:
            return cls(
                access_key_id=payload["accessKeyId"],
                secret_access_key=payload["secretAccessKey"],
                session_token=payload["sessionToken"],
                expiration=_parse_expiration(payload["expiration"]),
            )
        except KeyError as exc:
            raise ValueError(
                f"unexpected s3credentials response, missing {exc}: keys were {sorted(payload)}"
            ) from exc

    def expires_within(self, margin: timedelta, *, now: datetime | None = None) -> bool:
        return (now or _utcnow()) + margin >= self.expiration

    def as_boto3_kwargs(self) -> dict[str, str]:
        """Keyword arguments for ``boto3.client('s3', **kwargs)``."""
        return {
            "aws_access_key_id": self.access_key_id,
            "aws_secret_access_key": self.secret_access_key,
            "aws_session_token": self.session_token,
            "region_name": S3_REGION,
        }


class S3CredentialProvider:
    """Hands out valid ASF S3 credentials, refreshing them before they expire.

    Hold one per process and call ``credentials()`` wherever a client is built.
    Fetching is authenticated by ``~/.netrc`` the same way HTTPS downloads are.
    """

    def __init__(
        self,
        url: str = NISAR_S3_CREDENTIALS_URL,
        *,
        refresh_margin: timedelta = DEFAULT_REFRESH_MARGIN,
        session: requests.Session | None = None,
        policy: RetryPolicy = DEFAULT_RETRY_POLICY,
        now: Callable[[], datetime] = None,  # type: ignore[assignment]
    ):
        self.url = url
        self.refresh_margin = refresh_margin
        self.policy = policy
        self._session = session
        self._now = now or _utcnow
        self._cached: S3Credentials | None = None

    def credentials(self) -> S3Credentials:
        """Current credentials, fetching or refreshing when needed.

        Never returns a set that is already inside the refresh margin: a
        credential the endpoint minted stale (clock skew, or a cached upstream
        response) would otherwise be handed to a caller, 403 on first use,
        get invalidated, and be re-fetched identically — a tight loop the
        caller cannot see the cause of. Failing loudly here names the cause.
        """
        cached = self._cached
        if cached is not None and not cached.expires_within(self.refresh_margin, now=self._now()):
            return cached
        if cached is not None:
            logger.info("ASF S3 credentials expire at %s; refreshing", cached.expiration)
        fresh = self._fetch()
        if fresh.expires_within(self.refresh_margin, now=self._now()):
            raise RuntimeError(
                f"ASF s3credentials endpoint returned a credential expiring at "
                f"{fresh.expiration}, already inside the {self.refresh_margin} refresh "
                "margin — likely clock skew between this host and ASF, or a stale "
                "upstream cache. Check this machine's clock; retrying will not help "
                "until one of them changes."
            )
        self._cached = fresh
        return fresh

    def invalidate(self) -> None:
        """Force the next call to re-fetch, e.g. after an unexpected 403."""
        self._cached = None

    def _fetch(self) -> S3Credentials:
        response = get_with_retry(self.url, policy=self.policy, session=self._session)
        return S3Credentials.from_payload(response.json())


def _parse_expiration(raw: str) -> datetime:
    """Parse ASF's expiry stamp, which is ISO-ish but space-separated.

    Naive values are read as UTC: the endpoint documents UTC, and treating an
    unlabelled stamp as local time would put the refresh hours off in either
    direction depending on where the build runs.
    """
    try:
        parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"unparseable s3credentials expiration {raw!r}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _utcnow() -> datetime:
    return datetime.now(UTC)
