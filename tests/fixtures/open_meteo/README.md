# Open-Meteo fixtures

Real responses captured on 2026-11-01 with `curl`, except `error_rate_limited.json`. A 429 can't be
triggered on demand, so that body is synthetic: it uses Open-Meteo's `{"error": true, "reason": ...}` error
shape, and the reason text is the message quoted in open-meteo issue #438.

| File | Request |
|---|---|
| `geocode_warszawa.json` | `/v1/search?name=Warszawa&count=5&language=pl` |
| `geocode_springfield.json` | `/v1/search?name=Springfield&count=5&language=en` |
| `geocode_empty.json` | `/v1/search?name=Xyzzyqqplorf` (no `results` key at all) |
| `forecast_warsaw.json` | `/v1/forecast` for Warsaw, 2026-11-01 to 2026-11-03, daily + current |
| `forecast_error_date_out_of_range.json` | `/v1/forecast` with `start_date=2026-12-30` (HTTP 400) |
| `forecast_error_latitude.json` | `/v1/forecast?latitude=91` (HTTP 400) |
| `archive_warsaw.json` | `/v1/archive` for Warsaw, 2026-05-01 to 2026-05-02 |

Data: Open-Meteo.com (CC BY 4.0). Location data based on GeoNames.
