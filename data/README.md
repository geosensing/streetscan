# Data

`scripts/extract/import_tables.py` copied these tables from the application
repositories on 2026-11-12. `src/streetscan/sources.py` checks each against a
SHA-256 hash before any analysis.

| File | What it is | Source |
|---|---|---|
| `raw/gopro_images.csv` | One row per annotated video frame in Mumbai, Navi Mumbai, Bangalore and Delhi: counts of women and men on foot and on two-wheelers, GPS position, time, road class, street features | `geosensing/streetscope`, `data/<city>/analysis_data.parquet` |
| `raw/gopro_sample_points.csv` | The 1,000 sampled points per city and the itinerary each was assigned to | `geosensing/streetscope`, `sampling/<city>/itineraries/` (Delhi: `delhi_nn`; Mumbai: `itineraries-mumbai-city.csv`) |
| `raw/streetview_sample.csv` | The 7,000 locations drawn for Street View in Mumbai, Navi Mumbai and Delhi | `geosensing/streetsight`, `data/samples/all_cities.csv` |
| `raw/streetview_views.csv`, `raw/streetview_locations.csv` | Annotated Street View images (one per heading) and the same counts summed by location | `geosensing/streetsight`, `notebooks/outputs/v2/` |
| `raw/streetview_funnel.csv`, `raw/streetview_selection.csv` | Counts at each step from eligible road segments to annotated images, by city and by road class | `geosensing/streetsight`, `notebooks/outputs/v2/` |
| `raw/noise_readings.csv` | 465 sound-meter readings in Delhi, 28 April to 16 May 2026: minimum and maximum dB in the window, position, time, stop number, traffic-stop and traffic-jam flags, road class | `geosensing/soundscape`, `data/rider/export-2026-05-24/noise_logs.csv` joined to `output/rider/readings.json` |
| `raw/air_readings.csv` | 98 PM2.5 and CO2 readings on the same Delhi routes | `geosensing/streetaqi`, `src/streetaqi/data/delhi_readings.parquet` |

## What was left out

- Annotator email addresses.
- Image file paths and storage URLs. No images are in this repository.
- Street addresses reverse-geocoded from the reading positions; the positions themselves are kept.
- The rider's route plan, which holds a home address.

Positions are points on public roads. Each day's first and last noise readings
are spread across the city (5 to 24 km apart), so they do not mark where the
rider set out from.

## Known oddities

- `noise_readings.csv` has one reading entered twice (day 1, itinerary 11, note "1st stop") with the minimum and maximum reversed (84.1 and 60.7).
- `day` in the noise and air tables is the route-plan day, not the order of fieldwork: day 6 was ridden on 3 May and day 5 on 4 May.
