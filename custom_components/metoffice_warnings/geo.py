"""Geometry helpers: distance from a point to a warning's polygons.

The nearest point of each polygon is found in longitude/latitude space first;
only that single point is then converted to a distance in miles.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

EARTH_RADIUS_MILES = 3958.761

# A polygon is a list of linear rings (outer ring first, then holes); each ring
# is a list of (longitude, latitude) positions, as in GeoJSON.
Ring = Sequence[Sequence[float]]
Polygon = Sequence[Ring]
LonLat = tuple[float, float]


def _haversine_miles(a: LonLat, b: LonLat) -> float:
    """Return the great-circle distance in miles between two (lon, lat) points."""
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(min(1.0, math.sqrt(h)))


def _degrees_sq(a: LonLat, b: LonLat, lon_scale: float) -> float:
    """Return a squared distance between two (lon, lat) points, in degrees.

    Longitude differences are multiplied by `lon_scale` (cos of the latitude)
    so that east-west and north-south degrees are comparable. This is only
    used to rank candidate points; the real distance comes from
    `_haversine_miles`.
    """
    return ((a[0] - b[0]) * lon_scale) ** 2 + (a[1] - b[1]) ** 2


def _closest_on_segment(
    a: Sequence[float], b: Sequence[float], p: LonLat, lon_scale: float
) -> LonLat:
    """Return the (lon, lat) point on segment a-b nearest to p.

    Works on the segment in (scaled) degree space: p is projected onto the
    segment's line and clamped to its endpoints. A zero-length segment
    returns a.
    """
    dx, dy = (b[0] - a[0]) * lon_scale, b[1] - a[1]
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return a[0], a[1]
    t = ((p[0] - a[0]) * lon_scale * dx + (p[1] - a[1]) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    return a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])


def _closest_on_ring(ring: Ring, p: LonLat, lon_scale: float) -> LonLat | None:
    """Return the (lon, lat) point on the ring's edges nearest to p.

    The ring is treated as closed, so GeoJSON's repeated closing vertex is
    harmless. Returns None for an empty ring.
    """
    best: LonLat | None = None
    best_sq = math.inf
    for i in range(len(ring)):
        candidate = _closest_on_segment(
            ring[i], ring[(i + 1) % len(ring)], p, lon_scale
        )
        sq = _degrees_sq(candidate, p, lon_scale)
        if sq < best_sq:
            best, best_sq = candidate, sq
    return best


def _inside_ring(ring: Ring, p: LonLat) -> bool:
    """Return True if p lies inside the ring.

    Ray casting: a ray from p along +longitude crosses the ring's edges an
    odd number of times if and only if p is inside. Points exactly on an edge
    may fall either way; the edge's own nearest point is at distance zero
    anyway, so the result is the same.
    """
    x, y = p
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def closest_point_on_polygon(polygon: Polygon, p: LonLat) -> LonLat | None:
    """Return the (lon, lat) point of a polygon closest to p.

    If p is inside the polygon (inside the outer ring and not within a hole),
    p itself is returned. Otherwise the nearest point on any ring edge is
    returned. Returns None if the polygon has no usable ring.
    """
    rings = [r for r in polygon if len(r) >= 3]
    if not rings:
        return None
    if _inside_ring(rings[0], p) and not any(_inside_ring(h, p) for h in rings[1:]):
        return p
    lon_scale = math.cos(math.radians(p[1]))
    candidates = [_closest_on_ring(r, p, lon_scale) for r in rings]
    return min(
        (c for c in candidates if c is not None),
        key=lambda c: _degrees_sq(c, p, lon_scale),
        default=None,
    )


def distance_to_polygons_miles(
    polygons: Sequence[Polygon], lat: float, lon: float
) -> float | None:
    """Return miles from (lat, lon) to the nearest polygon; 0 if inside one.

    For each polygon the closest point is found in longitude/latitude space,
    and only then converted to miles with the haversine formula. Returns None
    if there is no usable geometry.
    """
    p = (lon, lat)
    distances = [
        _haversine_miles(p, closest)
        for polygon in polygons
        if (closest := closest_point_on_polygon(polygon, p)) is not None
    ]
    return min(distances, default=None)
