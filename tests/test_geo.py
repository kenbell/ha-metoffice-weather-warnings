"""Tests for polygon distance helpers."""

import pytest

from custom_components.metoffice_warnings.geo import distance_to_polygons_miles

SQUARE = [[[-0.5, 51.3], [-0.5, 51.7], [0.3, 51.7], [0.3, 51.3], [-0.5, 51.3]]]


def test_inside_is_zero() -> None:
    assert distance_to_polygons_miles([SQUARE], 51.5, -0.1) == 0.0


def test_outside_distance() -> None:
    # 0.1 degree of latitude north of the top edge is ~6.9 miles
    dist = distance_to_polygons_miles([SQUARE], 51.8, -0.1)
    assert 6.5 < dist < 7.3


def test_hole_counts_as_outside() -> None:
    hole = [[-0.1, 51.4], [-0.1, 51.6], [0.1, 51.6], [0.1, 51.4], [-0.1, 51.4]]
    assert distance_to_polygons_miles([[SQUARE[0], hole]], 51.5, 0.0) > 0


def test_no_geometry() -> None:
    assert distance_to_polygons_miles([], 51.5, 0.0) is None


def test_closest_point_is_nearest_edge_point() -> None:
    from custom_components.metoffice_warnings.geo import closest_point_on_polygon

    lon, lat = closest_point_on_polygon(SQUARE, (-0.1, 51.8))
    assert lon == pytest.approx(-0.1)
    assert lat == pytest.approx(51.7)
    assert closest_point_on_polygon(SQUARE, (-0.1, 51.5)) == (-0.1, 51.5)
