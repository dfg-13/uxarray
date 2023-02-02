import os
import numpy as np
import xarray as xr

from unittest import TestCase
from pathlib import Path

import xarray as xr
import uxarray as ux
import numpy.testing as nt

try:
    import constants
except ImportError:
    from . import constants

current_path = Path(os.path.dirname(os.path.realpath(__file__)))



class TestGrid(TestCase):

    ug_filename1 = current_path / "meshfiles" / "outCSne30.ug"
    ug_filename2 = current_path / "meshfiles" / "outRLL1deg.ug"
    ug_filename3 = current_path / "meshfiles" / "ov_RLL10deg_CSne4.ug"

    xr_ds1 = xr.open_dataset(ug_filename1)
    xr_ds2 = xr.open_dataset(ug_filename2)
    xr_ds3 = xr.open_dataset(ug_filename3)
    tgrid1 = ux.Grid(xr_ds1)
    tgrid2 = ux.Grid(xr_ds2)
    tgrid3 = ux.Grid(xr_ds3)

    def test_encode_as(self):
        """Reads a ugrid file and encodes it as `xarray.Dataset` in various
        types."""

        self.tgrid1.encode_as("ugrid")
        self.tgrid2.encode_as("ugrid")
        self.tgrid3.encode_as("ugrid")

        self.tgrid1.encode_as("exodus")
        self.tgrid2.encode_as("exodus")
        self.tgrid3.encode_as("exodus")

    def test_open_non_mesh2_write_exodus(self):
        """Loads grid files of different formats using uxarray's open_dataset
        call."""

        path = current_path / "meshfiles" / "mesh.nc"
        xr_grid = xr.open_dataset(path)
        grid = ux.Grid(xr_grid)

        grid.encode_as("exodus")

    def test_init_verts(self):
        """Create a uxarray grid from vertices and saves a ugrid file.

        Also, test kwargs for grid initialization
        """

        verts = np.array([[0, 0], [2, 0], [0, 2], [2, 2]])
        vgrid = ux.Grid(verts, vertices=True, islatlon=True, concave=False)

        assert (vgrid.source_grid == "From vertices")

        vgrid.encode_as("ugrid")

    def test_init_grid_var_attrs(self):
        """Tests to see if accessing variables through set attributes is equal
        to using the dict."""

        # Dataset with standard UGRID variable names
        # Coordinates
        xr.testing.assert_equal(
            self.tgrid1.Mesh2_node_x,
            self.tgrid1.ds[self.tgrid1.ds_var_names["Mesh2_node_x"]])
        xr.testing.assert_equal(
            self.tgrid1.Mesh2_node_y,
            self.tgrid1.ds[self.tgrid1.ds_var_names["Mesh2_node_y"]])
        # Variables
        xr.testing.assert_equal(
            self.tgrid1.Mesh2_face_nodes,
            self.tgrid1.ds[self.tgrid1.ds_var_names["Mesh2_face_nodes"]])

        # Dimensions
        n_nodes = self.tgrid1.Mesh2_node_x.shape[0]
        n_faces, n_face_nodes = self.tgrid1.Mesh2_face_nodes.shape

        self.assertEqual(n_nodes, self.tgrid1.nMesh2_node)
        self.assertEqual(n_faces, self.tgrid1.nMesh2_face)
        self.assertEqual(n_face_nodes, self.tgrid1.nMaxMesh2_face_nodes)

        # xr.testing.assert_equal(
        #     self.tgrid1.nMesh2_node,
        #     self.tgrid1.ds[self.tgrid1.ds_var_names["nMesh2_node"]])
        # xr.testing.assert_equal(
        #     self.tgrid1.nMesh2_face,
        #     self.tgrid1.ds[self.tgrid1.ds_var_names["nMesh2_face"]])

        # Dataset with non-standard UGRID variable names
        path = current_path / "meshfiles" / "mesh.nc"
        xr_grid = xr.open_dataset(path)
        grid = ux.Grid(xr_grid)
        xr.testing.assert_equal(grid.Mesh2_node_x,
                                grid.ds[grid.ds_var_names["Mesh2_node_x"]])
        xr.testing.assert_equal(grid.Mesh2_node_y,
                                grid.ds[grid.ds_var_names["Mesh2_node_y"]])
        # Variables
        xr.testing.assert_equal(grid.Mesh2_face_nodes,
                                grid.ds[grid.ds_var_names["Mesh2_face_nodes"]])
        # Dimensions
        n_nodes = grid.Mesh2_node_x.shape[0]
        n_faces, n_face_nodes = grid.Mesh2_face_nodes.shape

        self.assertEqual(n_nodes, grid.nMesh2_node)
        self.assertEqual(n_faces, grid.nMesh2_face)
        self.assertEqual(n_face_nodes, grid.nMaxMesh2_face_nodes)

    # def test_init_dimension_attrs(self):
    def test_build_face_edges_connectivity(self):
        """Tests to see if the generated face_edges_connectivity number match
        the calculated results from Euler formular."""
        ug_filename_list = [
            "outRLL1deg.ug","outCSne30.ug", "ov_RLL10deg_CSne4.ug"
        ]  #["outRLL1deg.ug", "outCSne30.ug", "ov_RLL10deg_CSne4.ug"]
        for ug_file_name in ug_filename_list:
            ug_filename1 = current_path / "meshfiles" / ug_file_name
            xr_tgrid1 = xr.open_dataset(str(ug_filename1))
            tgrid1 = ux.Grid(xr_tgrid1)
            mesh2_face_nodes = tgrid1.ds["Mesh2_face_nodes"][0:400,:].values
            # two_mesh2_face_nodes = []
            #
            # for egde in mesh2_face_nodes:
            #     if 2 in egde:
            #         two_mesh2_face_nodes.append(egde)
            #
            # two_mesh2_face_nodes = np.array(two_mesh2_face_nodes)
            # mesh2_face_nodes = two_mesh2_face_nodes



            tgrid1.build_face_edges_connectivity()
            mesh2_face_edges = tgrid1.ds.Mesh2_face_edges
            mesh2_edge_nodes = tgrid1.ds.Mesh2_edge_nodes

            # [Test] using old fashion
            mesh2_edge_nodes_set = set(
            )  # Use the set data structure to store Edge object (undirected)

            # Also generate the face_edge_connectivity:Mesh2_face_edges for the latlonbox building
            mesh2_face_edges = []


            # Loop over each face
            for face in mesh2_face_nodes:
                cur_face_edge = []
                # Loop over nodes in a face
                for i in range(0, face.size - 1):
                    # with _FillValue=-1 used when faces have fewer nodes than MaxNumNodesPerFace.
                    if (face[i] == -1 or face[i + 1] == -1) or (np.isnan(
                            face[i]) or np.isnan(face[i + 1])):
                        continue
                    # Two nodes are connected to one another if they’re adjacent in the array
                    mesh2_edge_nodes_set.add(frozenset({face[i], face[i + 1]}))
                    cur_face_edge.append([face[i], face[i + 1]])
                # Two nodes are connected if one is the first element of the array and the other is the last
                # First make sure to skip the dummy _FillValue=-1 node
                last_node = face.size - 1
                start_node = 0
                while (face[last_node] == -1 or
                       np.isnan(face[last_node])) and last_node > 0:
                    last_node -= 1
                while (face[start_node] == -1 or
                       np.isnan(face[start_node])) and start_node > 0:
                    start_node += 1
                if face[last_node] < 0 or face[last_node] < 0:
                    raise Exception('Invalid node index')
                mesh2_edge_nodes_set.add(
                    frozenset({face[last_node], face[start_node]}))
                cur_face_edge.append([face[last_node], face[start_node]])
                mesh2_face_edges.append(cur_face_edge)

            mesh2_edge_nodes_old_fashion = []
            for edge in mesh2_edge_nodes_set:
                mesh2_edge_nodes_old_fashion.append(list(edge))
            mesh2_edge_nodes_old_fashion = np.array(mesh2_edge_nodes_old_fashion, dtype=np.int)
            mesh2_edge_nodes_old_fashion.sort(axis=1)
            mesh2_edge_nodes_old_fashion =  mesh2_edge_nodes_old_fashion[np.argsort( mesh2_edge_nodes_old_fashion[:, 0])]
            mesh2_edge_nodes = mesh2_edge_nodes[np.argsort(mesh2_edge_nodes[:, 0])]
            mesh2_edge_nodes_old_fashion =  mesh2_edge_nodes_old_fashion[np.argsort( mesh2_edge_nodes_old_fashion[:, 1])]
            mesh2_edge_nodes = mesh2_edge_nodes[np.argsort(mesh2_edge_nodes[:, 1])].values
            intersection = np.array([x for x in set(tuple(x) for x in mesh2_edge_nodes_old_fashion) & set(tuple(x) for x in mesh2_edge_nodes)])
            set_vec = np.array(list(set(tuple(x) for x in mesh2_edge_nodes)))
            set_vec = set_vec[np.argsort( set_vec[:, 0])]
            intersection = intersection[np.argsort( intersection[:, 0])]

            # def _cal_same_first_nodes_size(edges, first_node):
            #     entire_group = np.count_nonzero(edges[:,0] == first_node)
            #     return entire_group
            #
            # group_sizes_vec = np.zeros(401)
            # # Calculate the each group of edges size:
            # for i in range(0,401):
            #     group_sizes_vec[i] = _cal_same_first_nodes_size(mesh2_edge_nodes, i)
            #
            # group_sizes_old = np.zeros(401)
            # # Calculate the each group of edges size:
            # for i in range(0,401):
            #     group_sizes_old[i] = _cal_same_first_nodes_size(mesh2_edge_nodes_old_fashion, i)





            # Assert if the mesh2_face_edges sizes are correct.
            self.assertEqual(mesh2_face_edges.sizes["nMesh2_face"],
                             mesh2_face_nodes.sizes["nMesh2_face"])
            self.assertEqual(mesh2_face_edges.sizes["nMaxMesh2_face_edges"],
                             mesh2_face_nodes.sizes["nMaxMesh2_face_nodes"])
            self.assertEqual(mesh2_face_edges.sizes["Two"], 2)


            num_edges = mesh2_face_edges.sizes["nMesh2_face_temp"] + tgrid1.ds[
                "Mesh2_node_x"].sizes["nMesh2_node"] - 2
            self.assertEqual(mesh2_edge_nodes.sizes["nMesh2_edge"], num_edges)

    # def test_Xugrid_connectivity(self):
    #     ug_filename_list = [
    #         "outCSne30.ug", "ov_RLL10deg_CSne4.ug"
    #     ]  #["outRLL1deg.ug", "outCSne30.ug", "ov_RLL10deg_CSne4.ug"]
    #     for ug_file_name in ug_filename_list:
    #         ug_filename1 = current_path / "meshfiles" / ug_file_name
    #         xr_tgrid1 = xr.open_dataset(str(ug_filename1))
    #         tgrid1 = ux.Grid(xr_tgrid1)
    #         face_edge_connectivity = tgrid1.edge_connectivity()
    #         pass


# TODO: Move to test_shpfile/scrip when implemented
# use external package to read?
# https://gis.stackexchange.com/questions/113799/how-to-read-a-shapefile-in-python

    def test_read_shpfile(self):
        """Reads a shape file and write ugrid file."""
        with self.assertRaises(RuntimeError):
            shp_filename = current_path / "meshfiles" / "grid_fire.shp"
            tgrid = ux.Grid(str(shp_filename))

    def test_read_scrip(self):
        """Reads a scrip file."""

        scrip_8 = current_path / "meshfiles" / "outCSne8.nc"
        ug_30 = current_path / "meshfiles" / "outCSne30.ug"

        # Test read from scrip and from ugrid for grid class
        xr_grid_s8 = xr.open_dataset(scrip_8)
        ux_grid_s8 = ux.Grid(xr_grid_s8)  # tests from scrip

        xr_grid_u30 = xr.open_dataset(ug_30)
        ux_grid_u30 = ux.Grid(xr_grid_u30)  # tests from ugrid


class TestIntegrate(TestCase):

    mesh_file30 = current_path / "meshfiles" / "outCSne30.ug"
    data_file30 = current_path / "meshfiles" / "outCSne30_vortex.nc"
    data_file30_v2 = current_path / "meshfiles" / "outCSne30_var2.ug"

    def test_calculate_total_face_area_triangle(self):
        """Create a uxarray grid from vertices and saves an exodus file."""
        verts = np.array([[0.57735027, -5.77350269e-01, -0.57735027],
                          [0.57735027, 5.77350269e-01, -0.57735027],
                          [-0.57735027, 5.77350269e-01, -0.57735027]])
        vgrid = ux.Grid(verts)

        # get node names for each grid object
        x_var = vgrid.ds_var_names["Mesh2_node_x"]
        y_var = vgrid.ds_var_names["Mesh2_node_y"]
        z_var = vgrid.ds_var_names["Mesh2_node_z"]

        vgrid.ds[x_var].attrs["units"] = "m"
        vgrid.ds[y_var].attrs["units"] = "m"
        vgrid.ds[z_var].attrs["units"] = "m"

        area_gaussian = vgrid.calculate_total_face_area(
            quadrature_rule="gaussian", order=5)
        nt.assert_almost_equal(area_gaussian, constants.TRI_AREA, decimal=3)

        area_triangular = vgrid.calculate_total_face_area(
            quadrature_rule="triangular", order=4)
        nt.assert_almost_equal(area_triangular, constants.TRI_AREA, decimal=1)

    def test_calculate_total_face_area_file(self):
        """Create a uxarray grid from vertices and saves an exodus file."""

        xr_grid = xr.open_dataset(str(self.mesh_file30))
        grid = ux.Grid(xr_grid)

        area = grid.calculate_total_face_area()

        nt.assert_almost_equal(area, constants.MESH30_AREA, decimal=3)

    def test_integrate(self):
        xr_grid = xr.open_dataset(self.mesh_file30)
        xr_psi = xr.open_dataset(self.data_file30)
        xr_v2 = xr.open_dataset(self.data_file30_v2)

        u_grid = ux.Grid(xr_grid)

        integral_psi = u_grid.integrate(xr_psi)
        integral_var2 = u_grid.integrate(xr_v2)

        nt.assert_almost_equal(integral_psi, constants.PSI_INTG, decimal=3)
        nt.assert_almost_equal(integral_var2, constants.VAR2_INTG, decimal=3)


class TestFaceAreas(TestCase):

    def test_compute_face_areas_geoflow_small(self):
        """Checks if the GeoFlow Small can generate a face areas output."""
        geoflow_small_grid = current_path / "meshfiles" / "geoflow-small" / "grid.nc"
        grid_1_ds = xr.open_dataset(geoflow_small_grid)
        grid_1 = ux.Grid(grid_1_ds)
        grid_1.compute_face_areas()

    def test_compute_face_areas_fesom(self):
        """Checks if the FESOM PI-Grid Output can generate a face areas
        output."""

        fesom_grid_small = current_path / "meshfiles" / "fesom" / "fesom.mesh.diag.nc"
        grid_2_ds = xr.open_dataset(fesom_grid_small)
        grid_2 = ux.Grid(grid_2_ds)
        grid_2.compute_face_areas()
