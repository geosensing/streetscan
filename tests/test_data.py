"""The raw tables must reproduce numbers the application repositories report."""

import re

import numpy as np
import pandas as pd
import pytest

from streetscan.config import RAW_FILES
from streetscan.sources import read_raw, verify_sources


def test_raw_files_match_hashes():
    verify_sources()


@pytest.mark.parametrize(
    "city, images, pedestrians, women_share",
    [
        ("mumbai", 2809, 12331, 19.1),
        ("navi_mumbai", 1999, 4645, 18.0),
        ("bangalore", 2015, 2311, 27.4),
        ("delhi", 2417, 3020, 19.8),
    ],
)
def test_gopro_matches_streetscope_readme(city, images, pedestrians, women_share):
    data = read_raw("gopro_images.csv").query("city == @city")
    assert len(data) == images
    assert data["total_pedestrians"].sum() == pedestrians
    share = 100 * data["women_count"].sum() / data["total_pedestrians"].sum()
    assert round(share, 1) == women_share


def test_noise_first_four_days_match_soundscape_manuscript():
    noise = read_raw("noise_readings.csv")
    assert len(noise) == 465
    early = noise.query("day <= 4")
    assert len(early) == 55
    assert early["itinerary_id"].nunique() == 12
    # The soundscape manuscript's 65.9 comes from reading the lower of the two
    # values as the minimum: one duplicated entry has them reversed.
    low = np.minimum(early["min_db"], early["max_db"])
    high = np.maximum(early["min_db"], early["max_db"])
    assert low.median() == 65.9
    assert high.median() == 95.4
    assert high.max() == 119.2
    assert round(100 * (early["min_db"] >= 55).mean(), 1) == 87.3
    assert round(100 * (early["max_db"] >= 100).mean(), 1) == 30.9


def test_streetview_matches_streetsight_funnel():
    funnel = read_raw("streetview_funnel.csv").set_index("city")
    views = read_raw("streetview_views.csv")
    for city, row in funnel.iterrows():
        assert (views["city"] == city).sum() == row["annotated_views"]


@pytest.mark.parametrize("name", sorted(RAW_FILES))
def test_no_identifying_columns_or_values(name):
    data = read_raw(name)
    banned = re.compile(r"mail|annotator|address|url|_path$|phone|device", re.I)
    assert not [column for column in data.columns if banned.search(column)]
    text = data.select_dtypes(include=["object", "string"])
    for column in text:
        values = text[column].dropna().astype(str)
        assert not values.str.contains(r"@|https?://", regex=True).any(), column


def test_sample_points_lie_where_the_frames_do():
    """Each city's drawn points and its video frames are in the same city."""
    points = read_raw("gopro_sample_points.csv")
    frames = read_raw("gopro_images.csv").query("gps_valid")
    assert not pd.isna(points[["lat", "lon"]]).any().any()
    for city, drawn in points.groupby("city"):
        seen = frames[frames["city"] == city]
        assert abs(drawn["lat"].median() - seen["gps_lat"].median()) < 0.2, city
        assert abs(drawn["lon"].median() - seen["gps_lon"].median()) < 0.2, city


def test_sample_sizes():
    sizes = read_raw("gopro_sample_points.csv").groupby("city").size()
    assert sizes.to_dict() == {
        "bangalore": 1000,
        "delhi": 1000,
        "mumbai": 1000,
        "navi_mumbai": 10000,
    }
    routed = read_raw("gopro_sample_points.csv").dropna(subset=["itinerary_id"])
    assert (routed["city"] == "navi_mumbai").sum() == 8126


def test_navi_mumbai_annotation_rate_is_even_across_videos():
    """A random subset of saved frames has the same rate in every video."""
    from scipy import stats

    videos = read_raw("gopro_extracted_frames.csv").query("city == 'navi_mumbai'")
    rate = videos["annotated"].sum() / videos["saved"].sum()
    expected = videos["saved"] * rate
    chi2 = ((videos["annotated"] - expected) ** 2 / (expected * (1 - rate))).sum()
    assert stats.chi2.sf(chi2, len(videos) - 1) > 0.05
