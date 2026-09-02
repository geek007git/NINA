"""Tool implementations: clock, weather and web search."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from conftest import FORECAST_RESPONSE, GEOCODE_RESPONSE, FakeHttp, run
from nina.errors import ToolError
from nina.tools import clock, weather, websearch

FIXED_NOW = datetime(2026, 9, 1, 13, 15, tzinfo=timezone.utc)


# --- clock ----------------------------------------------------------------


def test_current_time_in_utc() -> None:
    assert clock.current_time("UTC", now=FIXED_NOW) == (
        "It is 1:15 PM on Tuesday, 1 September 2026 in UTC (UTC)."
    )


@pytest.mark.parametrize(
    ("spoken", "expected_zone"),
    [
        ("IST", "Asia/Kolkata"),
        ("ist", "Asia/Kolkata"),
        ("chennai", "Asia/Kolkata"),
        ("New York", "America/New_York"),
        ("london", "Europe/London"),
        ("Asia/Tokyo", "Asia/Tokyo"),
        ("asia/tokyo", "Asia/Tokyo"),
        ("asia tokyo", "Asia/Tokyo"),
    ],
)
def test_timezone_aliases_resolve(spoken: str, expected_zone: str) -> None:
    assert clock.resolve_zone(spoken).key == expected_zone


def test_time_converts_correctly() -> None:
    result = clock.current_time("IST", now=FIXED_NOW)
    assert "6:45 PM" in result
    assert "Asia/Kolkata" in result


def test_midnight_and_noon_read_as_twelve() -> None:
    midnight = datetime(2026, 9, 1, 0, 5, tzinfo=timezone.utc)
    noon = datetime(2026, 9, 1, 12, 5, tzinfo=timezone.utc)
    assert "12:05 AM" in clock.current_time("UTC", now=midnight)
    assert "12:05 PM" in clock.current_time("UTC", now=noon)


def test_day_has_no_leading_zero() -> None:
    """'01 September' sounds wrong when spoken aloud."""
    assert "on Tuesday, 1 September" in clock.current_time("UTC", now=FIXED_NOW)


def test_naive_datetime_is_treated_as_utc() -> None:
    naive = datetime(2026, 9, 1, 13, 15)
    assert clock.current_time("UTC", now=naive) == clock.current_time("UTC", now=FIXED_NOW)


def test_unknown_timezone_raises_tool_error() -> None:
    with pytest.raises(ToolError, match="do not recognise"):
        clock.resolve_zone("Narnia")


# --- weather --------------------------------------------------------------


def _weather_http() -> FakeHttp:
    return FakeHttp({"geocoding-api": GEOCODE_RESPONSE, "api.open-meteo": FORECAST_RESPONSE})


def test_weather_reads_as_a_sentence() -> None:
    result = run(weather.get_weather("chennai", _weather_http()))
    assert result.startswith("In Chennai, Tamil Nadu, India it is 31 degrees Celsius")
    assert "partly cloudy" in result
    assert "feeling more like 38" in result
    assert "Today runs between 26 and 33 degrees." in result
    assert "45 percent" in result


def test_weather_geocodes_before_forecasting() -> None:
    http = _weather_http()
    run(weather.get_weather("chennai", http))
    assert "geocoding-api" in http.calls[0][1]
    assert "api.open-meteo" in http.calls[1][1]


def test_unknown_place_raises() -> None:
    http = FakeHttp({"geocoding-api": {"results": []}})
    with pytest.raises(ToolError, match="could not find a place"):
        run(weather.get_weather("Atlantis", http))


def test_empty_place_raises_without_a_request() -> None:
    http = FakeHttp({})
    with pytest.raises(ToolError, match="need a place name"):
        run(weather.get_weather("   ", http))
    assert http.calls == []


def test_missing_temperature_raises() -> None:
    http = FakeHttp({"geocoding-api": GEOCODE_RESPONSE, "api.open-meteo": {"current": {}}})
    with pytest.raises(ToolError, match="no usable readings"):
        run(weather.get_weather("chennai", http))


def test_calm_wind_is_omitted() -> None:
    current = {**FORECAST_RESPONSE["current"], "wind_speed_10m": 4}
    forecast = {**FORECAST_RESPONSE, "current": current}
    http = FakeHttp({"geocoding-api": GEOCODE_RESPONSE, "api.open-meteo": forecast})
    assert "kilometres per hour" not in run(weather.get_weather("chennai", http))


def test_low_rain_chance_is_omitted() -> None:
    daily = {**FORECAST_RESPONSE["daily"], "precipitation_probability_max": [5]}
    forecast = {**FORECAST_RESPONSE, "daily": daily}
    http = FakeHttp({"geocoding-api": GEOCODE_RESPONSE, "api.open-meteo": forecast})
    assert "precipitation" not in run(weather.get_weather("chennai", http))


@pytest.mark.parametrize(
    ("code", "phrase"), [(0, "clear"), (3, "overcast"), (95, "thunderstorming")]
)
def test_known_weather_codes(code: int, phrase: str) -> None:
    assert weather.describe_code(code) == phrase


@pytest.mark.parametrize("code", [None, "abc", 9999])
def test_unknown_weather_codes_degrade(code: object) -> None:
    assert weather.describe_code(code) == "hard to classify"


def test_place_label_deduplicates_repeated_names() -> None:
    label = weather.format_place({"name": "Singapore", "admin1": None, "country": "Singapore"})
    assert label == "Singapore"


# --- search ---------------------------------------------------------------


def test_duckduckgo_prefers_the_abstract() -> None:
    http = FakeHttp(
        {
            "duckduckgo": {
                "AbstractText": "Python is a programming language.",
                "AbstractSource": "Wikipedia",
            }
        }
    )
    result = run(websearch.search("python", http))
    assert result == "Python is a programming language. (source: Wikipedia)"


def test_duckduckgo_falls_back_through_fields() -> None:
    http = FakeHttp({"duckduckgo": {"AbstractText": "", "Answer": "42"}})
    assert run(websearch.search("meaning of life", http)) == "42"

    http = FakeHttp({"duckduckgo": {"Definition": "A definition."}})
    assert run(websearch.search("term", http)) == "A definition."

    http = FakeHttp({"duckduckgo": {"RelatedTopics": [{"Text": "A related topic."}]}})
    assert run(websearch.search("thing", http)) == "A related topic."


def test_empty_duckduckgo_result_raises() -> None:
    http = FakeHttp({"duckduckgo": {}})
    with pytest.raises(ToolError, match="nothing solid"):
        run(websearch.search("obscure query", http))


def test_tavily_uses_its_answer_and_sends_the_key() -> None:
    http = FakeHttp({"tavily": {"answer": "The answer.", "results": []}})
    result = run(websearch.search("q", http, provider="tavily", api_key="tv-key"))
    assert result == "The answer."
    assert http.calls[0][0] == "POST"


def test_tavily_falls_back_to_result_snippets() -> None:
    http = FakeHttp({"tavily": {"answer": "", "results": [{"content": "Snippet one."}]}})
    assert run(websearch.search("q", http, provider="tavily", api_key="k")) == "Snippet one."


def test_tavily_without_a_key_raises() -> None:
    with pytest.raises(ToolError, match="not configured"):
        run(websearch.search("q", FakeHttp({}), provider="tavily", api_key=""))


def test_search_disabled_provider_raises() -> None:
    with pytest.raises(ToolError, match="turned off"):
        run(websearch.search("q", FakeHttp({}), provider="none"))


def test_empty_query_raises_without_a_request() -> None:
    http = FakeHttp({})
    with pytest.raises(ToolError, match="need something to search"):
        run(websearch.search("  ", http))
    assert http.calls == []


def test_long_answers_are_truncated_at_a_sentence_boundary() -> None:
    long_text = ("Sentence one is here. " * 60).strip()
    http = FakeHttp({"duckduckgo": {"AbstractText": long_text}})
    result = run(websearch.search("q", http))
    assert len(result) <= websearch.MAX_SPOKEN_CHARS
    assert result.endswith(".")
