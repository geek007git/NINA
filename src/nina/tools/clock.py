"""Date and time, phrased for speech."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..errors import ToolError

#: Spoken shorthands people actually use, mapped to IANA zone names.
ZONE_ALIASES: dict[str, str] = {
    "": "UTC",
    "utc": "UTC",
    "gmt": "UTC",
    "ist": "Asia/Kolkata",
    "india": "Asia/Kolkata",
    "chennai": "Asia/Kolkata",
    "bangalore": "Asia/Kolkata",
    "bengaluru": "Asia/Kolkata",
    "mumbai": "Asia/Kolkata",
    "delhi": "Asia/Kolkata",
    "est": "America/New_York",
    "edt": "America/New_York",
    "new york": "America/New_York",
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "los angeles": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "cst": "America/Chicago",
    "chicago": "America/Chicago",
    "london": "Europe/London",
    "uk": "Europe/London",
    "bst": "Europe/London",
    "paris": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "cet": "Europe/Berlin",
    "tokyo": "Asia/Tokyo",
    "jst": "Asia/Tokyo",
    "singapore": "Asia/Singapore",
    "dubai": "Asia/Dubai",
    "sydney": "Australia/Sydney",
}


def resolve_zone(name: str) -> ZoneInfo:
    """Resolve a spoken timezone name to a :class:`ZoneInfo`.

    Accepts IANA names ("Asia/Kolkata"), common abbreviations ("IST"), and city
    names, because speech-to-text will never hand back a tidy IANA identifier.

    Raises:
        ToolError: if the zone cannot be resolved.
    """
    cleaned = " ".join(name.strip().split())
    key = cleaned.lower()

    if key in ZONE_ALIASES:
        return ZoneInfo(ZONE_ALIASES[key])

    # Try the raw value, then a best-effort IANA-style normalisation
    # ("asia/kolkata" and "asia kolkata" both become "Asia/Kolkata").
    candidates = [cleaned]
    if "/" in cleaned or " " in cleaned:
        parts = cleaned.replace(" ", "/").split("/")
        candidates.append("/".join(p.strip().title().replace(" ", "_") for p in parts if p.strip()))

    for candidate in candidates:
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            continue

    raise ToolError(f"I do not recognise the timezone {cleaned!r}")


def _spoken_hour(dt: datetime) -> str:
    """12-hour clock without a leading zero, which sounds wrong when spoken."""
    hour = dt.hour % 12 or 12
    meridiem = "AM" if dt.hour < 12 else "PM"
    return f"{hour}:{dt.minute:02d} {meridiem}"


def current_time(tz: str = "UTC", *, now: datetime | None = None) -> str:
    """Return the current date and time in ``tz`` as a spoken sentence.

    Args:
        tz: Timezone name, abbreviation, or city.
        now: Injectable clock, so tests are deterministic.

    Returns:
        A single sentence such as
        ``"It is 6:45 PM on Tuesday, 1 September 2026 in Asia/Kolkata (IST)."``
    """
    zone = resolve_zone(tz)
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    local = reference.astimezone(zone)

    abbrev = local.strftime("%Z")
    # %-d is not portable to Windows, so strip the zero by hand.
    day = str(local.day)
    date_part = f"{local.strftime('%A')}, {day} {local.strftime('%B %Y')}"
    suffix = f" ({abbrev})" if abbrev and not abbrev.startswith(("+", "-")) else ""
    return f"It is {_spoken_hour(local)} on {date_part} in {zone.key}{suffix}."
