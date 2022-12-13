"""uxarray grid module."""
import os
import xarray as xr
import numpy as np

# reader and writer imports
from ._exodus import _read_exodus, _encode_exodus
from ._ugrid import _read_ugrid, _encode_ugrid
from ._shapefile import _read_shpfile
from ._scrip import _read_scrip, _encode_scrip
from .helpers import get_all_face_area_from_coords, parse_grid_type, _convert_node_lonlat_rad_to_xyz, \
    _convert_node_xyz_to_lonlat_rad

int_dtype = np.uint32


class Grid:
    """
    Examples
    ----------

    Open an exodus file with Uxarray Grid object

    >>> xarray_obj = xr.open_dataset("filename.g")
    >>> mesh = ux.Grid(xarray_obj)

    Encode as a `xarray.Dataset` in the UGRID format

    >>> mesh.encode_as("ugrid")
    """

    def __init__(self, dataset, **kwargs):
        """Initialize grid variables, decide if loading happens via file, verts
        or gridspec.

        Parameters
        ----------
        dataset : xarray.Dataset, ndarray, list, tuple, required
            Input xarray.Dataset or vertex coordinates that form one face.

        Other Parameters
        ----------------
        islatlon : bool, optional
            Specify if the grid is lat/lon based
        concave: bool, optional
            Specify if this grid has concave elements (internal checks for this are possible)
        gridspec: bool, optional
            Specifies gridspec
        mesh_type: str, optional
            Specify the mesh file type, eg. exo, ugrid, shp, etc

        Raises
        ------
            RuntimeError
                If specified file not found
        """
        # initialize internal variable names
        self.__init_ds_var_names__()

        # initialize face_area variable
        self._face_areas = None

        # TODO: fix when adding/exercising gridspec

        # unpack kwargs
        # sets default values for all kwargs to None
        kwargs_list = [
            'gridspec', 'vertices', 'islatlon', 'concave', 'source_grid'
        ]
        for key in kwargs_list:
            setattr(self, key, kwargs.get(key, None))

        # check if initializing from verts:
        if isinstance(dataset, (list, tuple, np.ndarray)):
            self.vertices = dataset
            self.__from_vert__()
            self.source_grid = "From vertices"
        # check if initializing from string
        # TODO: re-add gridspec initialization when implemented
        elif isinstance(dataset, xr.Dataset):
            self.mesh_type = parse_grid_type(dataset)
            self.__from_ds__(dataset=dataset)
        else:
            raise RuntimeError("Dataset is not a valid input type.")

        # initialize convenience attributes
        self.__init_grid_var_attrs__()

    def __init_ds_var_names__(self):
        """Populates a dictionary for storing uxarray's internal representation
        of xarray object.

        Note ugrid conventions are flexible with names of variables, see:
        http://ugrid-conventions.github.io/ugrid-conventions/
        """
        self.ds_var_names = {
            "Mesh2": "Mesh2",
            "Mesh2_node_x": "Mesh2_node_x",
            "Mesh2_node_y": "Mesh2_node_y",
            "Mesh2_node_z": "Mesh2_node_z",
            "Mesh2_face_nodes": "Mesh2_face_nodes",
            # initialize dims
            "nMesh2_node": "nMesh2_node",
            "nMesh2_face": "nMesh2_face",
            "nMaxMesh2_face_nodes": "nMaxMesh2_face_nodes"
        }

    def __init_grid_var_attrs__(self) -> None:
        """Initialize attributes for directly accessing UGRID dimensions and
        variables.

        Examples
        ----------
        Assuming the mesh node coordinates for longitude are stored with an input
        name of 'mesh_node_x', we store this variable name in the `ds_var_names`
        dictionary with the key 'Mesh2_node_x'. In order to access it, we do:

        >>> x = grid.ds[grid.ds_var_names["Mesh2_node_x"]]

        With the help of this function, we can directly access it through the
        use of a standardized name based on the UGRID conventions

        >>> x = grid.Mesh2_node_x
        """

        # Iterate over dict to set access attributes
        for key, value in self.ds_var_names.items():
            # Set Attributes for Data Variables
            if self.ds.data_vars is not None:
                if value in self.ds.data_vars:
                    setattr(self, key, self.ds[value])

            # Set Attributes for Coordinates
            if self.ds.coords is not None:
                if value in self.ds.coords:
                    setattr(self, key, self.ds[value])

            # Set Attributes for Dimensions
            if self.ds.dims is not None:
                if value in self.ds.dims:
                    setattr(self, key, len(self.ds[value]))

    def __from_vert__(self):
        """Create a grid with one face with vertices specified by the given
        argument.

        Called by :func:`__init__`.
        """
        self.ds = xr.Dataset()
        self.ds["Mesh2"] = xr.DataArray(
            attrs={
                "cf_role": "mesh_topology",
                "long_name": "Topology data of unstructured mesh",
                "topology_dimension": -1,
                "node_coordinates": "Mesh2_node_x Mesh2_node_y Mesh2_node_z",
                "node_dimension": "nMesh2_node",
                "face_node_connectivity": "Mesh2_face_nodes",
                "face_dimension": "nMesh2_face"
            })
        self.ds.Mesh2.attrs['topology_dimension'] = self.vertices[0].size

        # set default coordinate units to spherical coordinates
        # users can change to cartesian if using cartesian for initialization
        x_units = "degrees_east"
        y_units = "degrees_north"
        if self.vertices[0].size > 2:
            z_units = "elevation"

        x_coord = self.vertices.transpose()[0]
        y_coord = self.vertices.transpose()[1]
        if self.vertices[0].size > 2:
            z_coord = self.vertices.transpose()[2]

        # single face with all nodes
        num_nodes = x_coord.size
        connectivity = [list(range(0, num_nodes))]

        self.ds["Mesh2_node_x"] = xr.DataArray(data=xr.DataArray(x_coord),
                                               dims=["nMesh2_node"],
                                               attrs={"units": x_units})
        self.ds["Mesh2_node_y"] = xr.DataArray(data=xr.DataArray(y_coord),
                                               dims=["nMesh2_node"],
                                               attrs={"units": y_units})
        if self.vertices[0].size > 2:
            self.ds["Mesh2_node_z"] = xr.DataArray(data=xr.DataArray(z_coord),
                                                   dims=["nMesh2_node"],
                                                   attrs={"units": z_units})

        self.ds["Mesh2_face_nodes"] = xr.DataArray(
            data=xr.DataArray(connectivity),
            dims=["nMesh2_face", "nMaxMesh2_face_nodes"],
            attrs={
                "cf_role": "face_node_connectivity",
                "_FillValue": -1,
                "start_index": 0
            })

    # load mesh from a file
    def __from_ds__(self, dataset):
        """Loads a mesh dataset."""
        # call reader as per mesh_type
        if self.mesh_type == "exo":
            self.ds = _read_exodus(dataset, self.ds_var_names)
        elif self.mesh_type == "scrip":
            self.ds = _read_scrip(dataset)
        elif self.mesh_type == "ugrid":
            self.ds, self.ds_var_names = _read_ugrid(dataset, self.ds_var_names)
        elif self.mesh_type == "shp":
            self.ds = _read_shpfile(dataset)
        else:
            raise RuntimeError("unknown mesh type")

        dataset.close()

    def encode_as(self, grid_type):
        """Encodes the grid as a new `xarray.Dataset` per grid format supplied
        in the `grid_type` argument.

        Parameters
        ----------
        grid_type : str, required
            Grid type of output dataset.
            Currently supported options are "ugrid", "exodus", and "scrip"

        Returns
        -------
        out_ds : xarray.Dataset
            The output `xarray.Dataset` that is encoded from the this grid.

        Raises
        ------
        RuntimeError
            If provided grid type or file type is unsupported.
        """

        if grid_type == "ugrid":
            out_ds = _encode_ugrid(self.ds)

        elif grid_type == "exodus":
            out_ds = _encode_exodus(self.ds, self.ds_var_names)

        elif grid_type == "scrip":
            out_ds = _encode_scrip(self.Mesh2_face_nodes, self.Mesh2_node_x,
                                   self.Mesh2_node_y, self.face_areas)
        else:
            raise RuntimeError("The grid type not supported: ", grid_type)

        return out_ds

    def calculate_total_face_area(self, quadrature_rule="triangular", order=4):
        """Function to calculate the total surface area of all the faces in a
        mesh.

        Parameters
        ----------
        quadrature_rule : str, optional
            Quadrature rule to use. Defaults to "triangular".
        order : int, optional
            Order of quadrature rule. Defaults to 4.

        Returns
        -------
        Sum of area of all the faces in the mesh : float
        """

        # call function to get area of all the faces as a np array
        face_areas = self.compute_face_areas(quadrature_rule, order)

        return np.sum(face_areas)

    def compute_face_areas(self, quadrature_rule="triangular", order=4):
        """Face areas calculation function for grid class, calculates area of
        all faces in the grid.

        Parameters
        ----------
        quadrature_rule : str, optional
            Quadrature rule to use. Defaults to "triangular".
        order : int, optional
            Order of quadrature rule. Defaults to 4.

        Returns
        -------
        Area of all the faces in the mesh : np.ndarray

        Examples
        --------
        Open a uxarray grid file

        >>> grid = ux.open_dataset("/home/jain/uxarray/test/meshfiles/outCSne30.ug")

        Get area of all faces in the same order as listed in grid.ds.Mesh2_face_nodes

        >>> grid.get_face_areas
        array([0.00211174, 0.00211221, 0.00210723, ..., 0.00210723, 0.00211221,
            0.00211174])
        """
        if self._face_areas is None:
            # area of a face call needs the units for coordinate conversion if spherical grid is used
            coords_type = "spherical"
            if not "degree" in self.Mesh2_node_x.units:
                coords_type = "cartesian"

            face_nodes = self.Mesh2_face_nodes.data.astype(int_dtype)
            dim = self.Mesh2.attrs['topology_dimension']

            # initialize z
            z = np.zeros((self.nMesh2_node))

            # call func to cal face area of all nodes
            x = self.Mesh2_node_x.data
            y = self.Mesh2_node_y.data
            # check if z dimension
            if self.Mesh2.topology_dimension > 2:
                z = self.Mesh2_node_z.data

            # call function to get area of all the faces as a np array
            self._face_areas = get_all_face_area_from_coords(
                x, y, z, face_nodes, dim, quadrature_rule, order, coords_type)

        return self._face_areas

    # use the property keyword for declaration on face_areas property
    @property
    def face_areas(self):
        """Declare face_areas as a property."""

        if self._face_areas is None:
            self.compute_face_areas()
        return self._face_areas

    def integrate(self, var_ds, quadrature_rule="triangular", order=4):
        """Integrates over all the faces of the given mesh.

        Parameters
        ----------
        var_ds : Xarray dataset, required
            Xarray dataset containing values to integrate on this grid
        quadrature_rule : str, optional
            Quadrature rule to use. Defaults to "triangular".
        order : int, optional
            Order of quadrature rule. Defaults to 4.

        Returns
        -------
        Calculated integral : float

        Examples
        --------
        Open grid file only

        >>> xr_grid = xr.open_dataset("grid.ug")
        >>> grid = ux.Grid.(xr_grid)
        >>> var_ds = xr.open_dataset("centroid_pressure_data_ug")

        # Compute the integral
        >>> integral_psi = grid.integrate(var_ds)
        """
        integral = 0.0

        # call function to get area of all the faces as a np array
        face_areas = self.compute_face_areas(quadrature_rule, order)

        var_key = list(var_ds.keys())
        if len(var_key) > 1:
            # warning: print message
            print(
                "WARNING: The xarray dataset file has more than one variable, using the first variable for integration"
            )
        var_key = var_key[0]
        face_vals = var_ds[var_key].to_numpy()
        integral = np.dot(face_areas, face_vals)

        return integral

    def _populate_cartesian_xyz_coord(self):
        """A helper function that populates the xyz attribute in UXarray.ds.
        This function is called when we need to use the cartesian coordinates
        for each node to do the calculation but the input data only has the
        "Mesh2_node_x" and "Mesh2_node_y" in degree.

        Note
        ----
        In the UXarray, we abide the UGRID convention and make sure the following attributes will always have its
        corresponding units as stated below:

        Mesh2_node_x
         unit:  "degree_east" for longitude
        Mesh2_node_y
         unit:  "degrees_north" for latitude
        Mesh2_node_z
         unit:  "m"
        Mesh2_node_cart_x
         unit:  "m"
        Mesh2_node_cart_y
         unit:  "m"
        Mesh2_node_cart_z
         unit:  "m"
        """

        # Check if the cartesian coordinates are already populated
        if "Mesh2_node_cart_x" in self.ds.keys():
            return

        # check for units and create Mesh2_node_cart_x/y/z set to self.ds
        num_nodes = self.ds.Mesh2_node_x.size
        node_cart_list_x = [0.0] * num_nodes
        node_cart_list_y = [0.0] * num_nodes
        node_cart_list_z = [0.0] * num_nodes
        for i in range(num_nodes):
            if "degree" in self.ds.Mesh2_node_x.units:
                node = [
                    np.deg2rad(self.ds["Mesh2_node_x"].values[i]),
                    np.deg2rad(self.ds["Mesh2_node_y"].values[i])
                ]  # [lon, lat]
                node_cart = _convert_node_lonlat_rad_to_xyz(node)  # [x, y, z]
                node_cart_list_x[i] = node_cart[0]
                node_cart_list_y[i] = node_cart[1]
                node_cart_list_z[i] = node_cart[2]

        self.ds["Mesh2_node_cart_x"] = xr.DataArray(data=node_cart_list_x)
        self.ds["Mesh2_node_cart_y"] = xr.DataArray(data=node_cart_list_y)
        self.ds["Mesh2_node_cart_z"] = xr.DataArray(data=node_cart_list_z)

    def _populate_lonlat_coord(self):
        """Helper function that populates the longitude and latitude and store
        it into the Mesh2_node_x and Mesh2_node_y. This is called when the
        input data has "Mesh2_node_x", "Mesh2_node_y", "Mesh2_node_z" in
        meters. Since we want "Mesh2_node_x" and "Mesh2_node_y" always have the
        "degree" units. For more details, please read the following.

        Note
        ----
        In the UXarray, we abide the UGRID convention and make sure the following attributes will always have its
        corresponding units as stated below:

        Mesh2_node_x
         unit:  "degree_east" for longitude
        Mesh2_node_y
         unit:  "degrees_north" for latitude
        Mesh2_node_z
         unit:  "m"
        Mesh2_node_cart_x
         unit:  "m"
        Mesh2_node_cart_y
         unit:  "m"
        Mesh2_node_cart_z
         unit:  "m"
        """
        # Check if the "Mesh2_node_x" is already in longitude
        if "degree" in self.ds.Mesh2_node_x.units:
            return
        num_nodes = self.ds.Mesh2_node_x.size
        node_latlon_list_lat = [0.0] * num_nodes
        node_latlon_list_lon = [0.0] * num_nodes
        node_cart_list_x = [0.0] * num_nodes
        node_cart_list_y = [0.0] * num_nodes
        node_cart_list_z = [0.0] * num_nodes
        for i in range(num_nodes):
            if "m" in self.ds.Mesh2_node_x.units:
                node = [
                    self.ds["Mesh2_node_x"].values[i],
                    self.ds["Mesh2_node_y"].values[i],
                    self.ds["Mesh2_node_z"].values[i]
                ]  # [x, y, z]
                node_lonlat = _convert_node_xyz_to_lonlat_rad(
                    node)  # [lon, lat]
                node_cart_list_x[i] = self.ds["Mesh2_node_x"].values[i]
                node_cart_list_y[i] = self.ds["Mesh2_node_y"].values[i]
                node_cart_list_z[i] = self.ds["Mesh2_node_z"].values[i]
                node_lonlat[0] = np.rad2deg(node_lonlat[0])
                node_lonlat[1] = np.rad2deg(node_lonlat[1])
                node_latlon_list_lon[i] = node_lonlat[0]
                node_latlon_list_lat[i] = node_lonlat[1]

        self.ds["Mesh2_node_cart_x"] = xr.DataArray(data=node_cart_list_x)
        self.ds["Mesh2_node_cart_y"] = xr.DataArray(data=node_cart_list_y)
        self.ds["Mesh2_node_cart_z"] = xr.DataArray(data=node_cart_list_z)
        self.ds["Mesh2_node_x"].values = node_latlon_list_lon
        self.ds["Mesh2_node_y"].values = node_latlon_list_lat
        self.ds.Mesh2_node_x.attrs["units"] = "degree_east"
        self.ds.Mesh2_node_y.attrs["units"] = "degrees_north"
