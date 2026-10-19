import logging
from dataclasses import dataclass
from typing import Any


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GeoLocation:
    country_code: str
    city: str


class GeoLocator:
    """Resolve local GeoLite2 data, falling back without making network calls."""

    def __init__(
        self,
        *,
        db_path: str | None,
        mock_country_code: str = "XX",
        mock_city: str = "Mock City",
        reader: Any | None = None,
    ) -> None:
        self._fallback = GeoLocation(mock_country_code, mock_city)
        self._reader = reader

        if self._reader is not None or not db_path:
            return

        try:
            from geoip2.database import Reader  # type: ignore[import-not-found]

            self._reader = Reader(db_path)
        except (ImportError, OSError) as error:
            logger.warning("Local GeoLite2 lookup unavailable; using mock fallback: %s", error)

    def resolve(self, ip_address: str | None) -> GeoLocation:
        if self._reader is None or not ip_address or ip_address == "unknown":
            return self._fallback

        try:
            response = self._reader.city(ip_address)
            country_code = getattr(getattr(response, "country", None), "iso_code", None)
            city = getattr(getattr(response, "city", None), "name", None)
            return GeoLocation(country_code or self._fallback.country_code, city or self._fallback.city)
        except Exception:  # A malformed/missing local record must not drop a click.
            logger.exception("Local GeoLite2 lookup failed; using mock fallback")
            return self._fallback

    def close(self) -> None:
        if self._reader is not None:
            close = getattr(self._reader, "close", None)
            if close is not None:
                close()
