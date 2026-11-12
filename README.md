# Sampling Streets: Design-Based Inference for Street-Level Field Measurement

Varun K.R. and Gaurav Sood

[Paper](ms/main.pdf) · [Data](data/README.md)

## Question and motivation

Researchers measure streets with cameras and sensors: who is visible in public, how loud a road is, how dirty the air is. Most such data come from wherever access was easy, such as platform imagery or routes a team could reach. Numbers from such data describe the places measured, not the city. This paper asks what it takes to make a street-level measurement a statement about a city: a list of streets to sample from, a random draw from that list, and standard errors that follow from the draw.

## Data and research design

The frame is the road network from OpenStreetMap, cut into segments. [geo-sampling](https://github.com/geosensing/geo-sampling) draws the sample, [allocator](https://github.com/geosensing/allocator) groups sampled points into field routes, and [geoestimate](https://github.com/geosensing/geoestimate) produces estimates and standard errors. Four applications use the tools:

- women's share of visible pedestrians from researcher-collected video in Mumbai, Navi Mumbai, Delhi and Bangalore ([streetscope](https://github.com/geosensing/streetscope));
- the same outcome from Google Street View in Mumbai, Navi Mumbai and Delhi ([streetsight](https://github.com/geosensing/streetsight));
- street noise in Delhi from a hand-held sound meter ([soundscape](https://github.com/geosensing/soundscape));
- street air quality in Delhi ([streetaqi](https://github.com/geosensing/streetaqi)).

## Key findings

The manuscript is a draft. Its numbers are not yet produced by this repository's pipeline, so none are repeated here.

## Reproduce

```
make restore
make check
```

The manuscript needs pdfLaTeX and latexmk.

## Files and pipeline

| Path | Contents |
|---|---|
| `ms/` | Manuscript and bibliography |
| `src/streetscan/` | Functions the stages share |
| `scripts/` | Numbered pipeline stages; `99_run_all.py` runs them in order |
| `scripts/extract/` | One-off importers from the application repositories; not part of the pipeline |
| `data/raw/` | Per-unit tables the analysis starts from |
| `tabs/`, `figs/` | Generated tables, macros and figures |
| `tests/` | Tests |
