#-------------------------------------------------------------------------------
# Name:        Matrix plot maker

# Purpose:     To make matrix plots from hand-digitized footprints
#
# Author:      T. Yeomans
#
# Created:     02-02-2024
# Notes:       For lines requires digitized footprint polygons which have NS or EW
#              as direction attributes, as well as Uni_ID, ecosite type, and line type for
#              later scripts.  For pads requires a polygon with a Uni_ID and ecosite.
# Outputs:     Matrix plots associated with footprints
#
#-------------------------------------------------------------------------------

import arcpy
import os
import csv
import math
import tempfile


#################### Matrix plots for lines

# Set up folders for the files
def setup_folders(root_folder):

    try:
        os.makedirs(root_folder)
        print("Folder %s created" % root_folder)

    except FileExistsError:
        print("Folder %s already exists" % root_folder)

    try:
        folder_list = ['Line_midpoint', 'Matrix_loc', 'Matrix_plots', 'Wellpad_matrix_loc', 'Wellpad_plots']
        for folder in folder_list:
            path = os.path.join(root_folder, folder)
            os.mkdir(path)

    except FileExistsError:
        print("Folders already exist")

    print ('Folders done.')


# A function to append the existing coordinates onto the existing digitized footprint shapefile
def calculate_polygon_center():

    # Set the workspace environment
    arcpy.env.workspace = arcpy.Describe(input_foot_shp).path

    # Add fields to store X and Y coordinates in the polygon attribute table
    arcpy.AddField_management(input_foot_shp, "Centroid_X", "DOUBLE")
    arcpy.AddField_management(input_foot_shp, "Centroid_Y", "DOUBLE")

    # Calculate the centroid coordinates and update the attribute table
    with arcpy.da.UpdateCursor(input_foot_shp, ["SHAPE@", "Centroid_X", "Centroid_Y"]) as cursor:
        for row in cursor:
            try:
                # Get the centroid coordinates directly from SHAPE@XY
                centroid_x, centroid_y = row[0].centroid.X, row[0].centroid.Y

                # Update the attribute table with centroid coordinates
                row[1] = centroid_x
                row[2] = centroid_y

                cursor.updateRow(row)
            except Exception as e:
                print(f"Error processing row {row[0]}: {e}")

    print("Centroid coordinates calculated and stored in the attribute table.")


# A function to create footprint centroid shapefiles
def create_point_shapefile():

    # Set the workspace environment
    arcpy.env.workspace = arcpy.Describe(input_foot_shp).path

    output_point_shp = folder_loc + r'\Line_midpoint\Centroid_Points.shp'

    # Create a point feature class with the same spatial reference as the input polygon shapefile
    spatial_reference = arcpy.Describe(input_foot_shp).spatialReference
    arcpy.management.CreateFeatureclass(os.path.dirname(output_point_shp), os.path.basename(output_point_shp), "POINT", spatial_reference=spatial_reference)

    # Get the field names from the input polygon shapefile
    field_names = [field.name for field in arcpy.ListFields(input_foot_shp)]

    # Add fields to the output point shapefile if they do not already exist
    for field_name in field_names:
        # Skip shape-related fields
        if field_name.lower() not in ["shape", "shape_length", "shape_area"]:
            if not arcpy.ListFields(output_point_shp, field_name):
                arcpy.AddField_management(output_point_shp, field_name, "TEXT")  # You can modify the field type as needed

    # Apply field mappings and calculate the centroid coordinates
    with arcpy.da.InsertCursor(output_point_shp, ["SHAPE@", "Centroid_X", "Centroid_Y"] + field_names) as cursor:
        with arcpy.da.SearchCursor(input_foot_shp, ["SHAPE@", "Centroid_X", "Centroid_Y"] + field_names) as search_cursor:
            for row in search_cursor:
                try:
                    # Create a point feature at the centroid coordinates
                    point = arcpy.Point(row[1], row[2])
                    point_geometry = arcpy.PointGeometry(point, spatial_reference)

                    # Insert the point feature into the output shapefile
                    cursor.insertRow([point_geometry, row[1], row[2]] + list(row[3:]))
                except Exception as e:
                    print(f"Error inserting row. Fields: {field_names}")
                    raise e

    print(f"Point shapefile created at: {output_point_shp}")


# A function to create bearing lines originating from the centerpoint and going orthogonal to the NS or EW direction specified in the attribute table
def create_bearing_lines():

    input_point_shp = folder_loc + r'\Line_midpoint\Centroid_Points.shp'

    bearing_line = folder_loc + r'\Matrix_loc\matrix_bearing.shp'

    #Set a line length that will extend beyond the edges of your digitzed sample, but not too long that it intersects with another
    length = 100

    # Set up the workspace
    arcpy.env.workspace = os.path.dirname(bearing_line)

    # Create a new line feature class
    arcpy.management.CreateFeatureclass(os.path.dirname(bearing_line), os.path.basename(bearing_line), "POLYLINE", spatial_reference=spatial_reference)

    # Add fields to the output line shapefile
    arcpy.AddField_management(bearing_line, "Direction", "TEXT")

    # Insert line features for each point in the input shapefile
    with arcpy.da.SearchCursor(input_point_shp, ["SHAPE@", "Direction"]) as search_cursor:
        with arcpy.da.InsertCursor(bearing_line, ["SHAPE@", "Direction"]) as insert_cursor:
            for row in search_cursor:
                try:
                    # Extract the point geometry and direction from the input point
                    point_geometry, direction = row[0], row[1]

                    # Create the line features.
                    # If the seismic line is oriented NS, the bearing line should be EW
                    # If the seismic line is oriented EW, the bearing line should be NS
                    if direction in ["E_W", "N_S"]:
                        if direction == "E_W":
                            start_point = arcpy.Point(point_geometry.centroid.X, point_geometry.centroid.Y - length/2)
                            end_point = arcpy.Point(point_geometry.centroid.X, point_geometry.centroid.Y + length/2)
                        else:
                            start_point = arcpy.Point(point_geometry.centroid.X - length/2, point_geometry.centroid.Y)
                            end_point = arcpy.Point(point_geometry.centroid.X + length/2, point_geometry.centroid.Y)

                        array = arcpy.Array([start_point, end_point])
                        line_geometry = arcpy.Polyline(array, spatial_reference)

                        # Insert the line feature into the output shapefile
                        insert_cursor.insertRow([line_geometry, direction])
                    else:
                        print(f"Ignoring point with unknown direction: {direction}")

                except Exception as e:
                    print(f"Error processing point: {e}")

    print(f"Bearing shapefile created at: {bearing_line}")


# A function to cut the bearing line where it intersects the edge of the digitized footprint
def bearing_clip_footprint():

    bearing_line = folder_loc + r'\\Matrix_loc\matrix_bearing.shp'
    bearing_line_clip = folder_loc + r'\Matrix_loc\bearing_clip.shp'

    try:
        arcpy.analysis.PairwiseIntersect(
            in_features=f"{bearing_line};{input_foot_shp}",
            out_feature_class=bearing_line_clip,
            join_attributes="ALL",
            cluster_tolerance=None,
            output_type="INPUT"
        )
        print("Bearing footprints clipped.")

    except arcpy.ExecuteError:
        print(arcpy.GetMessages(2))


# A function to extend lines to a specified distance in the matrix to locate the centerpoint of the matrix plot
def extend_lines(extension_length):

    bearing_lines_clip = folder_loc + r'\Matrix_loc\bearing_clip.shp'
    matrix_extended_line = folder_loc + r'\Matrix_loc\bearing_extended.shp'

    try:
        # Create the output shapefile path
        output_folder = os.path.dirname(matrix_extended_line)
        output_name = os.path.basename(matrix_extended_line)

        # Check if the output shapefile exists, create it if it doesn't
        if not arcpy.Exists(matrix_extended_line):
            arcpy.management.CreateFeatureclass(output_folder,
                                                output_name,
                                                "POLYLINE",
                                                spatial_reference=arcpy.Describe(bearing_lines_clip).spatialReference)

            # Add fields to store information
            arcpy.AddField_management(matrix_extended_line, "Id", "LONG")

        # Open an insert cursor to add extended lines
        with arcpy.da.InsertCursor(matrix_extended_line, ["SHAPE@", "Id"]) as insert_cursor:
            # Open a search cursor for the input lines shapefile
            with arcpy.da.SearchCursor(bearing_lines_clip, ["SHAPE@", "Id"]) as search_cursor:
                for row in search_cursor:
                    line_geometry, orig_id = row[0], row[1]

                    # Get the first and last points of the line
                    start_point = line_geometry.firstPoint
                    end_point = line_geometry.lastPoint

                    # Calculate new start and end points based on the extension length
                    # Ignore zero-length lines
                    if line_geometry.length == 0:
                        continue

                    # Calculate the angle of the line
                    angle = math.atan2(end_point.Y - start_point.Y, end_point.X - start_point.X)

                    # Extend the line in both directions
                    extended_start_point = arcpy.Point(start_point.X - extension_length * math.cos(angle),
                                                        start_point.Y - extension_length * math.sin(angle))
                    extended_end_point = arcpy.Point(end_point.X + extension_length * math.cos(angle),
                                                        end_point.Y + extension_length * math.sin(angle))

                    # Create a new line geometry with the extended points
                    extended_line_geometry = arcpy.Polyline(arcpy.Array([extended_start_point, end_point, extended_end_point]),
                                                            arcpy.Describe(bearing_lines_clip).spatialReference)

                    # Insert the extended line into the output shapefile
                    insert_cursor.insertRow([extended_line_geometry, orig_id])

        print("Lines extended to matrix plot center.")

    except arcpy.ExecuteError:
        print(arcpy.GetMessages(2))


# A function to assign the original shapefile attributes. Shape 1 is giving the attributes, shape 2 is recieving them
def intersect_and_transfer_attributes(input_shape1, input_shape2):

    try:
        # Create a unique temporary output file using the tempfile module
        temp_dir = tempfile.gettempdir()
        intersect_output = os.path.join(temp_dir, f"intersect_temp_{next(tempfile._get_candidate_names())}.shp")

        # Intersect point and line features
        arcpy.analysis.Intersect([input_shape1, input_shape2], intersect_output)

        # Transfer attributes from the intersect result to the line shapefile
        output_line_shp = input_shape2.replace(".shp", "_att.shp")
        arcpy.analysis.SpatialJoin(input_shape2, intersect_output, output_line_shp, "JOIN_ONE_TO_ONE", "KEEP_COMMON")

        print("Attributes transferred.")

    except arcpy.ExecuteError:
        print(arcpy.GetMessages(2))



# A function to create centerpoints for the matrix location plots
def create_points_at_line_ends(extended_lines, matrix_loc):



    try:
        # Set up the workspace
        arcpy.env.workspace = os.path.dirname(matrix_loc)

        # Create the output shapefile
        arcpy.management.CreateFeatureclass(os.path.dirname(matrix_loc),
                                            os.path.basename(matrix_loc),
                                            "POINT",
                                            spatial_reference=arcpy.Describe(extended_lines).spatialReference)

        # Add fields to store information
        arcpy.AddField_management(matrix_loc, "Id", "LONG")
        arcpy.AddField_management(matrix_loc, "End_Type", "TEXT")

        # Open an insert cursor to add points at both ends of the lines
        with arcpy.da.InsertCursor(matrix_loc, ["SHAPE@", "Id", "End_Type"]) as insert_cursor:
            # Open a search cursor for the input lines shapefile
            with arcpy.da.SearchCursor(extended_lines, ["SHAPE@", "Id"]) as search_cursor:
                for row in search_cursor:
                    line_geometry, orig_id = row[0], row[1]

                    # Get the first and last points of the line
                    start_point = line_geometry.firstPoint
                    end_point = line_geometry.lastPoint

                    # Create a point feature at the start of the line
                    start_point_geometry = arcpy.PointGeometry(start_point, arcpy.Describe(extended_lines).spatialReference)
                    insert_cursor.insertRow([start_point_geometry, orig_id, "Start"])

                    # Create a point feature at the end of the line
                    end_point_geometry = arcpy.PointGeometry(end_point, arcpy.Describe(extended_lines).spatialReference)
                    insert_cursor.insertRow([end_point_geometry, orig_id, "End"])

        print("Points created at both ends of the lines.")

    except arcpy.ExecuteError:
        print(arcpy.GetMessages(2))




# A function to create the matrix plots.  A plot radius needs to be specified.
def create_matrix_plots(matrix_loc, output_matrix_plot, plot_radius):

    try:
        # Set up the workspace
        arcpy.env.workspace = os.path.dirname(output_matrix_plot)

        # Create the output buffer shapefile
        arcpy.management.CreateFeatureclass(os.path.dirname(output_matrix_plot),
                                            os.path.basename(output_matrix_plot),
                                            "POLYGON",
                                            spatial_reference=arcpy.Describe(matrix_loc).spatialReference)

        # Add fields to store information
        arcpy.AddField_management(output_matrix_plot, "Id", "LONG")
        arcpy.AddField_management(output_matrix_plot, "End_Type", "TEXT")

        # Open an insert cursor to add buffer polygons
        with arcpy.da.InsertCursor(output_matrix_plot, ["SHAPE@", "Id", "End_Type"]) as insert_cursor:
            # Open a search cursor for the input points shapefile
            with arcpy.da.SearchCursor(matrix_loc, ["SHAPE@", "Id", "End_Type"]) as search_cursor:
                for row in search_cursor:
                    point_geometry, orig_id, end_type = row[0], row[1], row[2]

                    # Create a buffer around the point
                    buffer_geometry = point_geometry.buffer(plot_radius)

                    # Insert the buffer polygon into the output shapefile
                    insert_cursor.insertRow([buffer_geometry, orig_id, end_type])

        print(f"Buffers created and saved here: {output_matrix_plot}")

    except arcpy.ExecuteError:
        print(arcpy.GetMessages(2))

###################################################################################################################################
# Matrix plots for pads.  Some of the line functions are used in this process - see the bottom of this script for details


# Add a unique ID to each polygon in a shapefile for tracking purposes
def add_uniq_ID(input_shapefile):

    # Add a field for unique ID
    arcpy.management.AddField(input_shapefile, 'Uni_ID', 'LONG')
    id_num = 1

    # Iterate over each row in the attribute table to add a unique number
    with arcpy.da.UpdateCursor(input_shapefile, 'Uni_ID') as cursor:
        for row in cursor:
            row[0] = id_num
            cursor.updateRow(row)
            id_num += 1

    del cursor
    print('Unique IDs added')


# Create the matrix plot for each wellpad
# This will be a ring around each wellpad at a distance of 25 meters from the
# edge of the wellpad, with a width of 2 meters thick
# These distances match the BERA Field protocol document for seismic lines.
# They can be adjusted as necessary
def create_wellpad_matrix_ring_buffer(input_shapefile):

    output_folder = folder_loc + r'\Wellpad_matrix_loc'

    # Create the output folder if it does not exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)


    out_feature_class = output_folder +  r'\wellpads_matrix_ring.shp'

    # Create the buffer closest to the wellpad
    arcpy.analysis.Buffer(
        in_features = input_shapefile,
        out_feature_class = output_folder + r'\wellpads_24.shp',
        buffer_distance_or_field ='24 Meters',
        line_side = 'OUTSIDE_ONLY',
        line_end_type = 'ROUND',
        dissolve_option ='NONE',
        dissolve_field = None,
        method = 'PLANAR'
    )
    print('Inner buffer completed')

    # Create the buffer furthest from the wellapd
    arcpy.analysis.Buffer(
        in_features = input_shapefile,
        out_feature_class= output_folder + r'\wellpads_26.shp',
        buffer_distance_or_field='26 Meters',
        line_side = 'OUTSIDE_ONLY',
        line_end_type = 'ROUND',
        dissolve_option = 'NONE',
        dissolve_field = None,
        method = 'PLANAR'
    )
    print('Outer buffer completed')

    # Use the overlay tool to get the difference between the two layers
    arcpy.gapro.OverlayLayers(
    # The input_layer is the shapefile that is furthest away from the edge of the pad
    input_layer = output_folder + r'\wellpads_26.shp',
    overlay_layer = output_folder + r'\wellpads_24.shp',
    out_feature_class = out_feature_class,
    overlay_type ='ERASE'
    )
    print(f'Wellpad matrix ring completed and saved to {out_feature_class}')


### A function to create the bearing lines to where the matrix samples will be created
### This uses the original point file that the wellpad plots were generated from
def create_wellpad_mx_lines(input_point_shp):

    bearing_line = os.path.join(folder_loc, "Wellpad_matrix_loc", "SHL_mx_lines.shp")

    # Set a line length that will extend from the center of the wellpad and into the matrix at arpproximately the desired distance
    # Wellpads can be in many orientations, so the distance into the matrix will be different for different pads
    length = 100

    # Set up the workspace
    arcpy.env.workspace = os.path.dirname(bearing_line)

    # Get the spatial reference from the input point shapefile
    spatial_reference = arcpy.Describe(input_point_shp).spatialReference

    # Create a new line feature class with the same spatial reference as the input point shapefile
    arcpy.management.CreateFeatureclass(os.path.dirname(bearing_line), os.path.basename(bearing_line), "POLYLINE", spatial_reference=spatial_reference)

    # Insert line features for each point in the input shapefile
    with arcpy.da.SearchCursor(input_point_shp, ["SHAPE@"]) as search_cursor:
        with arcpy.da.InsertCursor(bearing_line, ["SHAPE@"]) as insert_cursor:
            for row in search_cursor:
                try:
                    # Extract the point geometry
                    point_geometry = row[0]

                    # Create the line features in all four cardinal directions
                    start_point_ew = arcpy.Point(point_geometry.centroid.X - length, point_geometry.centroid.Y)
                    end_point_ew = arcpy.Point(point_geometry.centroid.X + length, point_geometry.centroid.Y)
                    array_ew = arcpy.Array([start_point_ew, end_point_ew])
                    line_geometry_ew = arcpy.Polyline(array_ew)
                    insert_cursor.insertRow([line_geometry_ew])

                    start_point_ns = arcpy.Point(point_geometry.centroid.X, point_geometry.centroid.Y - length)
                    end_point_ns = arcpy.Point(point_geometry.centroid.X, point_geometry.centroid.Y + length)
                    array_ns = arcpy.Array([start_point_ns, end_point_ns])
                    line_geometry_ns = arcpy.Polyline(array_ns)
                    insert_cursor.insertRow([line_geometry_ns])



                except Exception as e:
                    print(f"Error processing point: {e}")

    print(f"Bearing shapefile created at: {bearing_line}")



## Run the create_points_at_line_ends function and the create_matrix_plots from the lines code to generate the points at line ends before moving onto the next function.

def intersect_and_transfer_attributes(input_shape1, input_shape2):
    try:
        # Create a unique temporary output file using the tempfile module
        temp_dir = tempfile.gettempdir()
        intersect_output = os.path.join(temp_dir, f"intersect_temp_{next(tempfile._get_candidate_names())}.shp")

        # Intersect point and line features
        arcpy.analysis.Intersect([input_shape1, input_shape2], intersect_output)

        # Check if intersection output contains features
        if arcpy.management.GetCount(intersect_output)[0] == '0':
            print("No features found in the intersection output.")
            return

        # Transfer attributes from the intersect result to the line shapefile
        output_line_shp = input_shape2.replace(".shp", "_att.shp")
        arcpy.analysis.SpatialJoin(input_shape2, intersect_output, output_line_shp, "JOIN_ONE_TO_ONE", "KEEP_COMMON")

        print("Attributes transferred.")

    except arcpy.ExecuteError:
        print(arcpy.GetMessages(2))
    except Exception as e:
        print(f"An error occurred: {str(e)}")





## Sample file locations
folder_loc = r'C:\BERA\00_Footprints_creation\Matrix_plots\2024_03_10'
input_foot_shp = r'C:\BERA\00_Footprints_creation\Lines\Sur_ranLine_100_edited_32612_PSSD.shp'
spatial_reference=arcpy.SpatialReference(26912)
input_pad_shp = r'C:\BERA\00_Footprints_creation\Lines\Sur_ranpad_100m_proj.shp'
input_pad_pt = r'C:\BERA\00_Footprints_creation\Samples\Working_Files\SHL_RanSamp_comb\Rand_SHL_comb.shp'





setup_folders(folder_loc)



 # Line matrix plot creation
calculate_polygon_center()
create_point_shapefile()
create_bearing_lines()
bearing_clip_footprint()
extend_lines(25)
intersect_and_transfer_attributes((folder_loc + r'\Line_midpoint\Centroid_Points.shp'), (folder_loc + r'\Matrix_loc\bearing_extended.shp'))
create_points_at_line_ends(folder_loc + r'\Matrix_loc\bearing_extended_att.shp', folder_loc + r'\Matrix_loc\matrix_loc.shp')
create_matrix_plots(folder_loc + r'\Matrix_loc\matrix_loc.shp', folder_loc + r'\Matrix_plots\matrix_plot.shp', 5.642)
intersect_and_transfer_attributes
intersect_and_transfer_attributes((folder_loc + r'\Matrix_loc\bearing_extended_att.shp'), (folder_loc + r'\Matrix_plots\matrix_plot.shp'))



 # Wellpad matrix plot creation
add_uniq_ID(input_pad_shp)
create_wellpad_matrix_ring_buffer(input_pad_shp)
create_wellpad_mx_lines(input_pad_pt)
intersect_and_transfer_attributes (input_pad_shp, folder_loc + r'\Wellpad_matrix_loc\SHL_mx_lines.shp')
create_points_at_line_ends(folder_loc + r'\Wellpad_matrix_loc\SHL_mx_lines_att.shp', folder_loc + r'\Wellpad_matrix_loc\SHL_matrix_loc.shp')
create_matrix_plots(folder_loc + r'\Wellpad_matrix_loc\SHL_matrix_loc.shp', folder_loc + r'\Wellpad_plots\SHL_matrix_plot_32612.shp', 5.642)
intersect_and_transfer_attributes(folder_loc + r'\Wellpad_matrix_loc\SHL_mx_lines_att.shp', folder_loc + r'\Wellpad_plots\SHL_matrix_plot_32612.shp' )




# At this point you can manually tidy the field names for the next step.
# Recommend to remove the centroid fields since it appliues to the line centroid, not the plot centroid.
# These can still be linked to the parent line segment with the Uni_ID
# There are several fields with temporary IDs and joins can be removed.