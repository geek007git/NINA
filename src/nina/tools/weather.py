"""Current conditions and a short forecast, via Open-Meteo.

Open-Meteo is used because it needs no API key and no account, so the tool works
the moment someone clones the repo. Both endpoints are free and keyless:
geocoding turns a spoken place name into coordinates, forecast turns coordinates
into conditions.
"""

from __future__ import annotations

from typing import Any

from ..errors import ToolError
from ..http_client import AsyncHttpClient

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

#: WMO weather interpretation codes, phrased for speech.
#: https://open-meteo.com/en/docs
WMO_CODES: dict[int, str] = {
    0: "clear",
    1: "mostly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "freezing fog",
    51: "drizzling lightly",
    53: "drizzling",
    55: "drizzling heavily",
    56: "freezing drizzle",
    57: "heavy freezing drizzle",
    61: "raining lightly",
    63: "raining",
    65: "raining heavily",
    66: "freezing rain",
    67: "heavy freezing rain",
    71: "snowing lightly",
    73: "snowing",
    75: "snowing heavily",
    77: "hailing snow grains",
    80: "with light rain showers",
    81: "with rain showers",
    82: "with violent rain showers",
    85: "with light snow showers",
    86: "with heavy snow showers",
    95: "thunderstorming",
    96: "thunderstorming with hail",
    99: "thunderstorming with heavy hail",
}


def describe_code(code: Any) -> str:
    """Turn a WMO code into a spoken phrase, tolerating junk input."""
    try:
        return WMO_CODES.get(int(code), "hard to classify")
    except (TypeError, ValueError):
        return "hard to classify"


def _round(value: Any) -> str | None:
    """Round a number for speech; returns ``None`` when the value is unusable."""
    try:
        return str(round(float(value)))
    except (TypeError, ValueError):
        return None


async def geocode(place: str, client: AsyncHttpClient) -> dict[str, Any]:
    """Resolve a place name to coordinates.

    Raises:
        ToolError: if the place is empty or cannot be found.
    """
    place = place.strip()
    if not place:
        raise ToolError("I need a place name to look up the weather")

    payload = await client.get_json(
        GEOCODE_URL, params={"name": place, "count": 1, "language": "en", "format": "json"}
    )
    results = (payload or {}).get("results") or []
    if not results:
        raise ToolError(f"I could not find a place called {place}")

    top: dict[str, Any] = results[0]
    if top.get("latitude") is None or top.get("longitude") is None:
        raise ToolError(f"I could not pin down where {place} is")
    return top


def format_place(result: dict[str, Any]) -> str:
    """Build a spoken place label, e.g. 'Chennai, Tamil Nadu, India'."""
    parts = [result.get("name"), result.get("admin1"), result.get("country")]
    seen: list[str] = []
    for part in parts:
        if part and part not in seen:
            seen.append(str(part))
    return ", ".join(seen)


async def get_weather(place: str, client: AsyncHttpClient) -> str:
    """Return current conditions plus today's range as a spoken sentence.

    Args:
        place: A city or region name.
        client: HTTP seam, injected for testability.

    Raises:
        ToolError: if the place is unknown or the service is unreachable.
    """
    location = await geocode(place, client)

    payload = await client.get_json(
        FORECAST_URL,
        params={
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "current": (
                "temperature_2m,apparent_temperature,relative_humidity_2m,"
                "weather_code,wind_speed_10m"
            ),
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "forecast_days": 1,
            "timezone": "auto",
        },
    )

    current = (payload or {}).get("current") or {}
    temp = _round(current.get("temperature_2m"))
    if temp is None:
        raise ToolError(f"I got no usable readings for {format_place(location)}")

    label = format_place(location)
    conditions = describe_code(current.get("weather_code"))
    sentence = f"In {label} it is {temp} degrees Celsius and {conditions}"

    feels = _round(current.get("apparent_temperature"))
    if feels is not None and feels != temp:
        sentence += f", feeling more like {feels}"

    wind = _round(current.get("wind_speed_10m"))
    if wind is not None and float(wind) >= 20:
        sentence += f", with wind at {wind} kilometres per hour"
    sentence += "."

    daily = (payload or {}).get("daily") or {}
    high = _first(daily.get("temperature_2m_max"))
    low = _first(daily.get("temperature_2m_min"))
    if high is not None and low is not None:
        sentence += f" Today runs between {low} and {high} degrees."

    rain = _first(daily.get("precipitation_probability_max"))
    if rain is not None and float(rain) >= 20:
        sentence += f" Chance of precipitation is {rain} percent."

    return sentence


def _first(series: Any) -> str | None:
    """Open-Meteo returns daily values as parallel arrays; take the first."""
    if isinstance(series, list) and series:
        return _round(series[0])
    return None
