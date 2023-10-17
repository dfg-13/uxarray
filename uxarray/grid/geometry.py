import numpy as np
from uxarray.grid.coordinates import node_lonlat_rad_to_xyz
from uxarray.constants import INT_DTYPE, INT_FILL_VALUE, ERROR_TOLERANCE
from uxarray.grid.connectivity import close_face_nodes
from uxarray.grid.intersections import gca_gca_intersection
import warnings

POLE_POINTS = {
    'North': np.array([0.0, 0.0, 1.0]),
    'South': np.array([0.0, 0.0, -1.0])
}


def _grid_to_polygons(grid, correct_antimeridian_polygons=True):
    """Constructs an array of Shapely Polygons representing each face, with
    antimeridian polygons split according to the GeoJSON standards.

     Parameters
    ----------
    grid : uxarray.Grid
        Grid Object
    correct_antimeridian_polygons: bool, Optional
        Parameter to select whether to correct and split antimeridian polygons

    Returns
    -------
    polygons : np.ndarray
        Array containing Shapely Polygons
    """

    # import optional dependencies
    import antimeridian
    from shapely import polygons as Polygons

    # obtain polygon shells for shapely polygon construction
    polygon_shells = _build_polygon_shells(grid.Mesh2_node_x.values,
                                           grid.Mesh2_node_y.values,
                                           grid.Mesh2_face_nodes.values,
                                           grid.nMesh2_face,
                                           grid.nMaxMesh2_face_nodes,
                                           grid.nNodes_per_face.values)

    # list of shapely Polygons representing each face in our grid
    polygons = Polygons(polygon_shells)

    # handle antimeridian polygons, if any
    if grid.antimeridian_face_indices is not None and correct_antimeridian_polygons:

        # obtain each antimeridian polygon
        antimeridian_polygons = polygons[grid.antimeridian_face_indices]

        # correct each antimeridian polygon
        corrected_polygons = [
            antimeridian.fix_polygon(P) for P in antimeridian_polygons
        ]

        # insert correct polygon back into original array
        for i in reversed(grid.antimeridian_face_indices):
            polygons[i] = corrected_polygons.pop()

    return polygons


def _build_polygon_shells(Mesh2_node_x, Mesh2_node_y, Mesh2_face_nodes,
                          nMesh2_face, nMaxMesh2_face_nodes, nNodes_per_face):
    """Constructs the shell of each polygon derived from the closed off face
    nodes, which can be used to construct Shapely Polygons.

    Coordinates should be in degrees, with the longitude being in the
    range [-180, 180].
    """

    # close face nodes to construct closed polygons
    closed_face_nodes = close_face_nodes(Mesh2_face_nodes, nMesh2_face,
                                         nMaxMesh2_face_nodes)

    # additional node after closing our faces
    nNodes_per_face_closed = nNodes_per_face + 1

    # longitude should be between [-180, 180]
    if Mesh2_node_x.max() > 180:
        Mesh2_node_x = (Mesh2_node_x + 180) % 360 - 180

    polygon_shells = []
    for face_nodes, max_n_nodes in zip(closed_face_nodes,
                                       nNodes_per_face_closed):

        polygon_x = np.empty_like(face_nodes, dtype=Mesh2_node_x.dtype)
        polygon_y = np.empty_like(face_nodes, dtype=Mesh2_node_x.dtype)

        polygon_x[0:max_n_nodes] = Mesh2_node_x[face_nodes[0:max_n_nodes]]
        polygon_y[0:max_n_nodes] = Mesh2_node_y[face_nodes[0:max_n_nodes]]

        polygon_x[max_n_nodes:] = polygon_x[0]
        polygon_y[max_n_nodes:] = polygon_y[0]

        cur_polygon_shell = np.array([polygon_x, polygon_y])
        polygon_shells.append(cur_polygon_shell.T)

    return np.array(polygon_shells)


# TODO: Update this one
def _build_corrected_polygon_shells(polygon_shells):
    """Constructs ``corrected_polygon_shells`` and
    ``Grid.original_to_corrected), representing the polygon shells, with
    antimeridian polygons split.

     Parameters
    ----------
    grid : uxarray.Grid
        Grid Object

    Returns
    -------
    corrected_polygon_shells : np.ndarray
        Array containing polygon shells, with antimeridian polygons split
    _corrected_shells_to_original_faces : np.ndarray
        Original indices used to map the corrected polygon shells to their entries in face nodes
    """

    # import optional dependencies
    import antimeridian
    from shapely import Polygon

    # list of shapely Polygons representing each Face in our grid
    polygons = [Polygon(shell) for shell in polygon_shells]

    # List of Polygons (non-split) and MultiPolygons (split across antimeridian)
    corrected_polygons = [antimeridian.fix_polygon(P) for P in polygons]

    _corrected_shells_to_original_faces = []
    corrected_polygon_shells = []

    for i, polygon in enumerate(corrected_polygons):

        # Convert MultiPolygons into individual Polygon Vertices
        if polygon.geom_type == "MultiPolygon":
            for individual_polygon in polygon.geoms:
                corrected_polygon_shells.append(
                    np.array([
                        individual_polygon.exterior.coords.xy[0],
                        individual_polygon.exterior.coords.xy[1]
                    ]).T)
                _corrected_shells_to_original_faces.append(i)

        # Convert Shapely Polygon into Polygon Vertices
        else:
            corrected_polygon_shells.append(
                np.array([
                    polygon.exterior.coords.xy[0], polygon.exterior.coords.xy[1]
                ]).T)
            _corrected_shells_to_original_faces.append(i)

    original_to_corrected = np.array(_corrected_shells_to_original_faces,
                                     dtype=INT_DTYPE)

    return corrected_polygon_shells, _corrected_shells_to_original_faces


def _build_antimeridian_face_indices(grid):
    """Constructs ``antimeridian_face_indices``, which represent the indicies
    of faces that cross the antimeridian.

     Parameters
    ----------
    grid : uxarray.Grid
        Grid Object

    Returns
    -------
    antimeridian_face_indices : np.ndarray
        Array containing Shapely Polygons
    """
    polygon_shells = _build_polygon_shells(grid.Mesh2_node_x.values,
                                           grid.Mesh2_node_y.values,
                                           grid.Mesh2_face_nodes.values,
                                           grid.nMesh2_face,
                                           grid.nMaxMesh2_face_nodes,
                                           grid.nNodes_per_face.values)

    antimeridian_face_indices = np.argwhere(
        np.any(np.abs(np.diff(polygon_shells[:, :, 0])) >= 180, axis=1))

    # convert output into a 1D array
    if antimeridian_face_indices.shape[0] == 1:
        antimeridian_face_indices = antimeridian_face_indices[0]
    else:
        antimeridian_face_indices = antimeridian_face_indices.squeeze()
    return antimeridian_face_indices


def _grid_to_polygon_geodataframe(grid, correct_antimeridian_polygons=True):
    """Constructs and returns a ``spatialpandas.GeoDataFrame``"""

    # import optional dependencies
    from spatialpandas.geometry import MultiPolygonArray
    from spatialpandas import GeoDataFrame

    # obtain faces represented as polygons, corrected on the antimeridian
    polygons = _grid_to_polygons(grid, correct_antimeridian_polygons)

    # prepare geometry for GeoDataFrame
    geometry = MultiPolygonArray(polygons)

    # assign geometry
    gdf = GeoDataFrame({"geometry": geometry})

    return gdf


def _grid_to_matplotlib_polycollection(grid):
    """Constructs and returns a ``matplotlib.collections.PolyCollection``"""

    # import optional dependencies
    from matplotlib.collections import PolyCollection

    polygon_shells = _build_polygon_shells(grid.Mesh2_node_x.values,
                                           grid.Mesh2_node_y.values,
                                           grid.Mesh2_face_nodes.values,
                                           grid.nMesh2_face,
                                           grid.nMaxMesh2_face_nodes,
                                           grid.nNodes_per_face.values)

    corrected_polygon_shells, corrected_to_original_faces = _build_corrected_polygon_shells(
        polygon_shells)

    return PolyCollection(corrected_polygon_shells), corrected_to_original_faces


def _grid_to_matplotlib_linecollection(grid):
    """Constructs and returns a ``matplotlib.collections.LineCollection``"""

    # import optional dependencies
    from matplotlib.collections import LineCollection

    # obtain corrected shapely polygons
    polygons = grid.to_shapely_polygons(correct_antimeridian_polygons=True)

    # Convert polygons into lines
    lines = []
    for pol in polygons:
        boundary = pol.boundary
        if boundary.geom_type == 'MultiLineString':
            for line in list(boundary.geoms):
                lines.append(np.array(line.coords))
        else:
            lines.append(np.array(boundary.coords))

    # need transform? consider adding it later if needed
    return LineCollection(lines)


def _pole_point_inside_polygon(pole, face_edge_cart):
    """Determines if a pole point is inside a polygon. For notice: if the pole
    point is on the edge of the polygon, our function will consider it as
    "inside the polygon". To use this function, the given face cannot reach out
    the other hemisphere. For example, if you want to check if the North pole
    is inside a polygon, the polygon should not reach the south hemisphere.

    Parameters
    ----------
    pole : str
        Either 'North' or 'South'
    face_edge_cart : np.ndarray
        Face polygon that is represented by a list of edges in Cartesian coordinates.
        The shape of the array is (n_edges, 2, 3)

    Returns
    -------
    bool
        True if pole point is inside polygon, False otherwise.

    Raises
    ------
    ValueError
        If the provided pole point is neither 'North' nor 'South'.

    Warning
    -----
    UserWarning
        To use this function, the given face cannot reach out the other hemisphere. For example, if you
        want to check if the North pole is inside a polygon, the polygon should not reach the south hemisphere.
    """
    if pole not in POLE_POINTS:
        raise ValueError('Pole point must be either "North" or "South"')

    # Classify the polygon's location
    location = _classify_polygon_location(face_edge_cart)

    pole_point = POLE_POINTS[pole]
    ref_point = np.array([1.0, 0.0, 0.0])  # Reference point on the equator

    ref_edge = np.array([pole_point, ref_point])

    if location == pole:
        # Case where the pole and the polygon are in the same hemisphere
        intersection_count = 0
        for edge in face_edge_cart:
            intersection_point = gca_gca_intersection(ref_edge, edge)

            if intersection_point.size != 0:
                if np.allclose(intersection_point, pole_point, atol=ERROR_TOLERANCE):
                    return True
                intersection_count += 1

        return intersection_count % 2 != 0

    elif location == "Equator":
        # Case where the polygon crosses the equator
        north_edges = face_edge_cart[np.any(face_edge_cart[:, :, 2] > 0, axis=1)]
        south_edges = face_edge_cart[np.any(face_edge_cart[:, :, 2] < 0, axis=1)]

        intersection_count = 0

        for edge in north_edges:
            intersection_point = gca_gca_intersection(ref_edge, edge)

            if intersection_point.size != 0:
                if np.allclose(intersection_point, pole_point, atol=ERROR_TOLERANCE):
                    return True
                intersection_count += 1

        for edge in south_edges:
            intersection_point = gca_gca_intersection(ref_edge, edge)

            if intersection_point.size != 0:
                if np.allclose(intersection_point, pole_point, atol=ERROR_TOLERANCE):
                    return True
                intersection_count += 1

        return intersection_count % 2 != 0

    else:
        # Case where the pole and the polygon are in opposite hemispheres
        return False


def _check_intersection(ref_edge, edges):
    """Check if the reference edge intersects with any of the given edges.
    """
    pole_point, ref_point = ref_edge
    intersection_count = 0

    for edge in edges:
        intersection_point = gca_gca_intersection(ref_edge, edge)

        if intersection_point.size != 0:
            if np.allclose(intersection_point, pole_point, atol=ERROR_TOLERANCE):
                return True
            intersection_count += 1

    return intersection_count

def _classify_polygon_location(face_edge_cart):
    """Classify the location of the polygon relative to the hemisphere."""
    z_coords = face_edge_cart[:, :, 2]
    if np.all(z_coords > 0):
        return "North"
    elif np.all(z_coords < 0):
        return "South"
    else:
        return "Equator"
