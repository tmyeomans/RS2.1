#-------------------------------------------------------------------------------
# Name:    Sampling script
# Purpose: To stratify sample wellpads, pipeline corridors and seismic lines.
#          Careful digitzation of samples will be required after this step.
#
# Author:      T. Yeomans
#
# Created:     01-01-2024
#
# Input data: Linear feature shapefiles with line size if desired, wellpad
#             polyons or surface hole locations, ecosite vector layer, and a systematic sampling grid
# Outputs:  Locations to perform detail digitzation for sampling, wellpad plots
#-------------------------------------------------------------------------------

import arcpy
import random
import os
import tempfile


# Set up folders for the files
# After setting up the folders, you will need to save the shapefiles for the linear feautres, wellpads, ecosites and systematic grid into the 'Source Files' folder
def setup_folders(root_folder):

    try:
        os.makedirs(root_folder)
        print("Folder %s created" % root_folder)

    except FileExistsError:
        print("Folder %s already exists" % root_folder)

    try:
        folder_list = ['Source_files', 'Working_Files']
        for folder in folder_list:
            path = os.path.join(root_folder, folder)
            os.mkdir(path)

    except FileExistsError:
        print("Folders already exist")

    print('Save your lines, wellpads, systematic grid and ecosites in the source files folder before moving to the next step.')


def get_orientation(input_line_shapefile):

    arcpy.env.workspace = r'C:\BERA\00_Footprint_creation\Working_files'
    line_shapefile = input_line_shapefile
    arcpy.env.outputCoordinateSystem = arcpy.Describe(line_shapefile).spatialReference

    # Get the bearing and length of lines and add them to a new field in the original file
    arcpy.management.CalculateGeometryAttributes(line_shapefile, [["bearing", "LINE_BEARING"], ["length", "LENGTH"]])
    print ('Bearing and length added')
    print ('Getting directions...')

    # Create a field to hold the direction
    arcpy.management.AddField(line_shapefile, "direction", "TEXT", field_length=50)

    # Get the direction based on bearing
    fields = ["SHAPE@", "bearing", "length", "direction"]
    with arcpy.da.UpdateCursor(line_shapefile, fields) as cursor:
        for row in cursor:
            bearing = row[1]

            # Define directions.
            # You can adjust these to meet narrower criteria as needed.
            # Note that N-S needs three entries to cover the ranges because it wraps past 360 degrees
            direction_ranges = {
                (0, 22.5): "N_S",
                (157.5, 202.5): "N_S",
                (337.5, 360): "N_S",
                (67.5, 112.5): "E_W",
                (247.5, 292.5): "E_W",
                (22.5, 67.5):   "SW_NE",
                (202.5, 247.5): "SW_NE",
                (112.5, 157.5): "NW_SE",
                (292.5, 337.5): "NW_SE",
            }

            # Check which range the bearing falls into
            for range, direction in direction_ranges.items():
                if range[0] <= bearing <= range[1]:
                    row[3] = direction
                    break
            else:
                row[3] = "Unknown"

            cursor.updateRow(row)

    print('Directions added')


# Function to create a generalized ecosite from S. Nielsen's work and save each ecosite polygon into a new shapefile.
# Other users will need to rewrite this function for their own ecosite polygons
def add_ecosite(input_ecosite_layer, output_folder):
    # Create a field to hold the ecosite
    arcpy.management.AddField(input_ecosite_layer, "ecosite", "TEXT", field_length=50)
    fields = ['gridcode', 'ecosite']

    with arcpy.da.UpdateCursor(input_ecosite_layer, fields) as cursor:
        for row in cursor:
            gridcode = row[0]

            # Below are the gridcodes grouped for genearlized ecosites based on S. Nielsen's documentation
            # Adjust these as necessary
            gridcode_ecosite_mapping = {
                (20, 21, 22): "UD",
                (10, 11, 12): "UM",
                (30, 31, 32): "T",
                (40, 41, 42): "WT",
                (50, 51, 52): "LDT"
            }

            # Find the ecosite corresponding to the gridcode
            assigned_ecosite = "Unknown"
            for gridcode_range, ecosite in gridcode_ecosite_mapping.items():
                if isinstance(gridcode_range, int):
                    if gridcode == gridcode_range:
                        assigned_ecosite = ecosite
                        break
                else:
                    if gridcode in gridcode_range:
                        assigned_ecosite = ecosite
                        break

            #Update the ecosite data field
            row[1] = assigned_ecosite
            cursor.updateRow(row)

    print('Generalized ecosites updated')

    # Create an output folder for the polygons if it doesn't already exist
    os.makedirs(output_folder, exist_ok=True)

    # Create a feature layer for the input layer
    input_layer_name = "input_layer"
    arcpy.management.MakeFeatureLayer(input_ecosite_layer, input_layer_name)

    # Create separate shapefiles for each ecosite
    with arcpy.da.SearchCursor(input_ecosite_layer, 'ecosite') as search_cursor:
        ecosite_values = set(row[0] for row in search_cursor if row[0] is not None)

    for ecosite_value in ecosite_values:
        output_shapefile = os.path.join(output_folder, f'{ecosite_value}_poly.shp')
        sql_expression = f"ecosite = '{ecosite_value}'"
        arcpy.management.MakeFeatureLayer(input_ecosite_layer, "temp_layer", where_clause=sql_expression)
        arcpy.management.CopyFeatures("temp_layer", output_shapefile)
        arcpy.management.Delete("temp_layer")
        arcpy.management.ClearWorkspaceCache()

    print(f'Shapefiles created for each ecosite in {output_folder}')


# This function clips the linear features by ecosite to make the data easier to manage
def clip_lines_by_ecosite(ecosite_folder, input_line_shapefile, output_folder):
    # Create the output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)

    # Iterate over ecosite shapefiles
    for ecosite_file in os.listdir(ecosite_folder):
        if ecosite_file.endswith("_poly.shp") and "unknown_poly" not in ecosite_file.lower():
            ecosite_path = os.path.join(ecosite_folder, ecosite_file)

            # Define the output shapefile path based on the ecosite name
            ecosite_name = os.path.splitext(ecosite_file)[0].replace("_poly", "")
            output_shapefile = os.path.join(output_folder, f'{ecosite_name}_lines.shp')

            # Clip the input line shapefile by the ecosite polygon
            arcpy.analysis.Clip(input_line_shapefile, ecosite_path, output_shapefile)

            # Add a new field for ecosite in the clipped lines shapefile
            arcpy.management.AddField(output_shapefile, "ecosite", "TEXT", field_length=50)

            # Calculate the ecosite field with the corresponding value
            arcpy.management.CalculateField(output_shapefile, "ecosite", f"'{ecosite_name}'", "PYTHON3")

            print(f'Lines clipped by {ecosite_name}. Output saved to {output_shapefile}')


# This code creates separate line shapefiles for each strata you are sampling over (ecosite + line width + direction)
def create_strata(input_folder, output_folder):
    arcpy.env.workspace = input_folder
    arcpy.env.overwriteOutput = True  # Allow overwriting of existing files

    # Create a common output folder so that subsequent functions can run over all files
    common_output_folder = output_folder
    os.makedirs(common_output_folder, exist_ok=True)

    # Iterate over line shapefiles in the input folder
    for line_shapefile in os.listdir(input_folder):
        if line_shapefile.endswith(".shp"):
            line_shapefile_path = os.path.join(input_folder, line_shapefile)

            # Extract ecosite name from the file path or file name
            ecosite_name = os.path.splitext(os.path.basename(line_shapefile))[0]

            # Create a feature layer for the input line shapefile
            input_layer_name = "input_layer"
            arcpy.management.MakeFeatureLayer(line_shapefile_path, input_layer_name)

            # Extract unique values from the 'line_type' and 'direction' fields
            line_types = set(row[0] for row in arcpy.da.SearchCursor(line_shapefile_path, 'line_type') if row[0] is not None)
            directions = set(row[0] for row in arcpy.da.SearchCursor(line_shapefile_path, 'direction') if row[0] is not None)

            # Create shapefiles based on unique combinations of 'line_type' and 'direction'
            for line_type in line_types:
                for direction in directions:
                    # Remove invalid characters from line_type and direction
                    clean_line_type = arcpy.ValidateFieldName(line_type, common_output_folder)
                    clean_direction = arcpy.ValidateFieldName(direction, common_output_folder)

                    # Remove the first instance of "_lines_" from the output shapefile name
                    output_shapefile = os.path.join(common_output_folder, f'{ecosite_name}_{clean_line_type}_{clean_direction}.shp')
                    sql_expression = f"line_type = '{line_type}' AND direction = '{direction}'"

                    arcpy.management.MakeFeatureLayer(line_shapefile_path, "temp_layer", where_clause=sql_expression)
                    arcpy.management.CopyFeatures("temp_layer", output_shapefile)
                    arcpy.management.Delete("temp_layer")
                    arcpy.management.ClearWorkspaceCache()

                    print(f'Shapefile created for ecosite: {ecosite_name}, line_type: {clean_line_type}, direction: {clean_direction}. Output saved to {output_shapefile}')



# This code will clip lines based on the cells of systematic grid and generate new shapefiles
# New shapefiles will not be created for cells that do not have lines in them
def systematically_clip_lines(input_line_shapefile, systematic_grid_shapefile, output_folder):
    # Create the output folder if it does not exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # In this case, we are only interested in N-S and E-W lines.
    # Check if the input_line_shapefile contains "NW_SE" or "SW_NE" and skip if true
    if "NW_SE" in input_line_shapefile or "SW_NE" in input_line_shapefile:
        print(f"Skipping {input_line_shapefile}")
        return

    # Iterate over each grid cell
    with arcpy.da.SearchCursor(systematic_grid_shapefile, ['SHAPE@', 'GRID_ID']) as cursor:
        for row in cursor:
            grid_cell_geometry = row[0]
            grid_id = row[1]

            # Create a layer to perform a spatial selection
            if arcpy.Exists("temp_layer"):
                arcpy.Delete_management("temp_layer")

            arcpy.management.MakeFeatureLayer(input_line_shapefile, "temp_layer")

            # Select features that intersect with the current grid cell
            arcpy.SelectLayerByLocation_management("temp_layer", "INTERSECT", grid_cell_geometry)

            # Check if there are selected features
            count = arcpy.management.GetCount("temp_layer")[0]

            # Skip if the grid cell is empty.
            # If this isn't done an empty shapefile will be created which upsets the random point generation script.
            if int(count) == 0:
                print(f"Skipping empty grid cell {grid_id}")
                continue

            # Get the base filename without the extension
            base_filename = arcpy.Describe(input_line_shapefile).baseName

            # Output path for the clipped shapefile
            output_path = os.path.join(output_folder, f'{base_filename}_{grid_id}.shp')

            # Perform the clip operation
            arcpy.analysis.Clip("temp_layer", grid_cell_geometry, output_path)

            print(f"Clipped shapefile saved to {output_path}")

    # Clean up the temporary layer outside the loop
    if arcpy.Exists("temp_layer"):
        arcpy.Delete_management("temp_layer")


# Run this with the previous function to clip all lines
def clip_all_lines(input_folder, systematic_grid_shapefile, output_folder):
    for filename in os.listdir(input_folder):
        if filename.endswith('.shp'):
            input_line_shapefile = os.path.join(input_folder, filename)

            # Call the clip_lines function
            systematically_clip_lines(input_line_shapefile, systematic_grid_shapefile, output_folder)

    print('All files lines clipped.')


# Code to randomly sample lines when used in combination with the following function.
# Minor clean-up of the data was done before this step, removing lines that fell in facility areas or had segments over wellpads
# The Delete Duplicates tool was run in ArcPro to remove accidential duplicates from the FLM process
# Missing lines in key strata were added (ex. wide pipeline corridors)
def ran_sample_line(input_line_shapefile, output_folder):
    # Specify the location for the output files
    arcpy.env.workspace = output_folder

    line_shapefile = input_line_shapefile

    # Create the output folder if it does not exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # Create an output shapefile for the random points using the name of the input shapefile
    base_filename = arcpy.Describe(line_shapefile).baseName
    output_points_name = f'{base_filename}_rndpt.shp'.replace(" ", "_").replace("-", "_")
    output_points_path = os.path.join(output_folder, output_points_name)

    # Create a new point feature class
    arcpy.CreateFeatureclass_management(output_folder, output_points_name, 'POINT')

    # Add a field to store a line identification number
    arcpy.AddField_management(output_points_path, 'LineID', 'LONG')

    # Set the number of points you want to sample
    target_num_points = 30
    current_num_points = 0

    # Open an insert cursor for the new point feature class
    cursor = arcpy.da.InsertCursor(output_points_path, ['SHAPE@', 'LineID'])
    try:
        # Iterate over this section until the target number of points has been sampled
        while current_num_points < target_num_points:

            # Randomly shuffle the lines
            lines_order = [row[0] for row in arcpy.da.SearchCursor(line_shapefile, 'SHAPE@')]
            random.shuffle(lines_order)

            # Iterate through the shuffled lines
            for line_id, line in enumerate(lines_order):
                # Generate a random distance along the line
                distance = random.uniform(0, 1)

                # Create a point at that location
                point = line.positionAlongLine(distance, True)

                # Insert the point and line identifier number into the output feature class
                cursor.insertRow([point, line_id])
                current_num_points += 1

                # Break the loop if the target number of sample points has been reached
                if current_num_points >= target_num_points:
                    break
    except:
        pass

    finally:
        # Ensure the cursor is closed even if an exception occurs
        del cursor

    print(f"{target_num_points} points generated and saved to {output_points_path}")


# Run this with the previous function to sample all lines.
def sample_all_lines(input_folder):

    # Specify the location for the output shapefiles
    output_folder = os.path.join(folder_loc + r'\Working_Files\Syst_Random_Pts')

    # Create the output folder if it does not exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # Iterate over each input_line_shapefile within a folder
    # input_folder = folder_loc + r'\Working_Files\Stratified_lines'
    for filename in os.listdir(input_folder):
        if filename.endswith('.shp'):
            input_line_shapefile = os.path.join(input_folder, filename)
            ran_sample_line(input_line_shapefile, output_folder)



############ Wellpad functions


# A function to create shapefiles for SHL by ecosite.  Note that not all of the wellpad may exist in that ecosite
# The input wellpad shapefile has been manually edited to remove pads that intersected facilities and infrastructure
# Irregular pads with multi wells were also removed.
def assign_ecosite_to_shl(shl_shapefile):
    # Specify the output coordinate system WKID
    target_coordinate_system_wkid = 26912

    # Create the output folder if it doesn't exist
    output_folder = os.path.join(folder_loc, 'Working_Files', 'SHL_Ecosite')
    os.makedirs(output_folder, exist_ok=True)

    ecosite_folder = os.path.join(folder_loc, 'Working_Files', 'Ecosite_polys')

    # Add the ecosite field to the SHL shapefile
    field_names = [field.name for field in arcpy.ListFields(shl_shapefile)]
    if "ecosite" not in field_names:
        arcpy.management.AddField(shl_shapefile, "ecosite", "TEXT", field_length=50)

    # Iterate over each ecosite shapefile in the folder
    for ecosite_file in os.listdir(ecosite_folder):
        if ecosite_file.endswith("_poly.shp") and "unknown_poly" not in ecosite_file.lower():
            ecosite_path = os.path.join(ecosite_folder, ecosite_file)

            # Define the output shapefile path based on the ecosite name
            ecosite_name = os.path.splitext(ecosite_file)[0].replace("_poly", "")
            output_shl_with_ecosite = os.path.join(output_folder, f'SHL_{ecosite_name}.shp')

            print(f"Processing ecosite: {ecosite_name}")

            # Make sure the existing layer is deleted before creating it again
            shl_layer_name = "shl_layer"
            if arcpy.Exists(shl_layer_name):
                arcpy.Delete_management(shl_layer_name)

            # Make a feature layer for the SHL shapefile
            arcpy.MakeFeatureLayer_management(shl_shapefile, shl_layer_name)

            # Make a feature layer for the ecosite shapefile
            ecosite_layer_name = f"ecosite_layer_{ecosite_name}"
            arcpy.MakeFeatureLayer_management(ecosite_path, ecosite_layer_name)

            # Select SHL features that intersect with the ecosite polygon
            arcpy.SelectLayerByLocation_management(shl_layer_name, "INTERSECT", ecosite_layer_name)

            # Update ecosite field for selected features
            with arcpy.da.UpdateCursor(shl_layer_name, ["ecosite"]) as cursor:
                for row in cursor:
                    row[0] = ecosite_name
                    cursor.updateRow(row)

            # Save the updated SHL shapefile
            arcpy.CopyFeatures_management(shl_layer_name, output_shl_with_ecosite)

            # Clear the selection on SHL shapefile
            arcpy.SelectLayerByAttribute_management(shl_layer_name, "CLEAR_SELECTION")

    print("Surface hole locations with ecosites complete.")



# A function to build a shapefile for each ecosite, for each grid cell
def grid_shl_ecosites():

    output_folder = (folder_loc + r'\Working_Files\Grid_stratified_SHL')
    shl_ecosites_folder = (folder_loc + r'\Working_Files\SHL_Ecosite')

    # Create the output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)

    # Iterate over each SHL_ecosite shapefile in the folder
    for shl_ecosite_file in os.listdir(shl_ecosites_folder):
        if shl_ecosite_file.endswith(".shp"):
            shl_ecosite_path = os.path.join(shl_ecosites_folder, shl_ecosite_file)

            # Get the ecosite name from the file name
            ecosite_name = os.path.splitext(shl_ecosite_file)[0].replace("SHL_", "")

            # Create a feature layer for the SHL_ecosite shapefile
            shl_ecosite_layer_name = f"shl_ecosite_layer_{ecosite_name}"  # Use a unique name
            arcpy.MakeFeatureLayer_management(shl_ecosite_path, shl_ecosite_layer_name)

            # Add a field to store the grid cell name
            arcpy.AddField_management(shl_ecosite_layer_name, "Grid_ID", "TEXT", field_length=50)

            # Iterate over each grid cell
            with arcpy.da.SearchCursor(systematic_grid_shapefile, ['SHAPE@', 'GRID_ID']) as cursor:
                for row in cursor:
                    grid_cell_geometry = row[0]
                    grid_id = row[1]

                    # Create a layer to perform a spatial selection
                    if arcpy.Exists("temp_layer"):
                        arcpy.Delete_management("temp_layer")

                    arcpy.management.MakeFeatureLayer(shl_ecosite_path, "temp_layer")

                    # Select features that intersect with the current grid cell
                    arcpy.SelectLayerByLocation_management("temp_layer", "INTERSECT", grid_cell_geometry)

                    # Check if there are selected features
                    count = arcpy.management.GetCount("temp_layer")[0]

                    # Skip if the grid cell is empty.
                    if int(count) == 0:
                        print(f"Skipping empty grid cell {grid_id} for ecosite {ecosite_name}")
                        continue

                    # Output path for the clipped shapefile
                    output_path = os.path.join(output_folder, f'SHL_{ecosite_name}_{grid_id}.shp')

                    # Perform the clip operation
                    arcpy.analysis.Clip("temp_layer", grid_cell_geometry, output_path)

                    # Update the Grid_Cell_Name field in the output shapefile
                    with arcpy.da.UpdateCursor(output_path, "Grid_ID") as update_cursor:
                        for update_row in update_cursor:
                            update_row[0] = f"{grid_id}"
                            update_cursor.updateRow(update_row)

                    print(f"Clipped SHL_ecosite shapefile for ecosite {ecosite_name} in grid cell {grid_id}. Output saved to {output_path}")

            # Clean up the temporary layer outside the loop
            if arcpy.Exists("temp_layer"):
                arcpy.Delete_management("temp_layer")



# A funtion to randomly sample the SHL
def random_sample_shl():

    # Specify the WKID for the target coordinate system
    target_coordinate_system_wkid = 26912

    input_grid_strat_SHL_folder = os.path.join(folder_loc, 'Working_Files', 'Grid_stratified_SHL')
    output_folder = os.path.join(folder_loc, 'Working_Files', 'Syst_rand_SHL')

    # Check if the output folder exists; if not, create it
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # Number of features to sample
    num_features_to_sample = 5

    # Iterate over each shapefile in the input folder
    for root, dirs, files in arcpy.da.Walk(input_grid_strat_SHL_folder, datatype="FeatureClass"):
        for file in files:
            input_grid_strat_SHL = os.path.join(root, file)

            # Check if the input shapefile exists
            if not arcpy.Exists(input_grid_strat_SHL):
                print(f"Skipping non-existent input shapefile: {input_grid_strat_SHL}")
                continue

            # Check if the feature class is a multipoint feature class
            desc = arcpy.Describe(input_grid_strat_SHL)
            if desc.shapeType != 'Multipoint':
                print(f"Skipping non-multipoint feature class: {input_grid_strat_SHL}")
                continue

            # Get the total number of features in the input shapefile
            total_features = int(arcpy.management.GetCount(input_grid_strat_SHL).getOutput(0))

            # Check if there are features to sample
            if total_features == 0:
                print(f"Skipping empty shapefile: {input_grid_strat_SHL}")
                continue

            # Generate a random list of the features to sample
            sampled_list = random.sample(range(total_features), min(num_features_to_sample, total_features))

            # Check if there are features to sample
            if not sampled_list:
                print(f"No features selected for random sampling in {input_grid_strat_SHL}")
                continue

            # Create an output shapefile for the random samples using the name of the input shapefile
            base_filename = os.path.splitext(os.path.basename(input_grid_strat_SHL))[0]
            output_path = os.path.join(output_folder, f'{base_filename}_rndsample.shp')

            # Create a new feature class for the randomly sampled features
            arcpy.CreateFeatureclass_management(output_folder, os.path.basename(output_path), 'MULTIPOINT', input_grid_strat_SHL)

            # Define the projection for the output feature class
            arcpy.management.DefineProjection(output_path, arcpy.SpatialReference(target_coordinate_system_wkid))

            # Open an insert cursor for the new feature class
            with arcpy.da.InsertCursor(output_path, ['SHAPE@'] + [field.name for field in arcpy.ListFields(input_grid_strat_SHL) if field.type != 'OID' and field.name != 'Licence']) as cursor:

                # Open a search cursor for the input shapefile
                with arcpy.da.SearchCursor(input_grid_strat_SHL, ['SHAPE@'] + [field.name for field in arcpy.ListFields(input_grid_strat_SHL) if field.type != 'OID' and field.name != 'Licence']) as search_cursor:
                    for index, row in enumerate(search_cursor):

                        # If the current feature number is in the randomly sampled list, insert it into the output shapefile
                        if index in sampled_list:
                            cursor.insertRow(row)

            print(f"Features randomly sampled and saved to {output_path}")



# A function to combine the individual systematically stratified samples together into one shapefile
def combine_shapefiles():


    output_folder = folder_loc + r'\Working_Files\SHL_RanSamp_comb'

    # Create the output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)

    input_folder = folder_loc + r'\Working_Files\Syst_rand_SHL'

    output_shapefile = output_folder + r'\Rand_SHL_comb.shp'

    # Create a list to hold the paths of all input shapefiles
    input_shapefiles = []

    # Walk through the input folder and collect all shapefiles
    for root, dirs, files in arcpy.da.Walk(input_folder, datatype="FeatureClass"):
        for file in files:
            if file.endswith('.shp'):
                input_shapefiles.append(os.path.join(root, file))

    # Check if there are any shapefiles found
    if not input_shapefiles:
        print("No input shapefiles found.")
        return

    # Create the output folder if it doesn't exist
    output_folder = os.path.dirname(output_shapefile)
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # Get the fields of the first input shapefile
    fields = [field.name for field in arcpy.ListFields(input_shapefiles[0]) if field.type not in ['Geometry', 'OID']]

    # Create a new feature class to hold the combined features
    arcpy.management.CreateFeatureclass(os.path.dirname(output_shapefile), os.path.basename(output_shapefile),
                                        "MULTIPOINT", spatial_reference=input_shapefiles[0])

    # Add the attribute fields to the output shapefile
    for field in fields:
        arcpy.management.AddField(output_shapefile, field, "TEXT")

    # Open an insert cursor for the output shapefile
    with arcpy.da.InsertCursor(output_shapefile, ['SHAPE@'] + fields) as cursor:
        # Iterate over each input shapefile
        for input_shapefile in input_shapefiles:
            # Open a search cursor for the current input shapefile
            with arcpy.da.SearchCursor(input_shapefile, ['SHAPE@'] + fields) as search_cursor:
                # Iterate over each feature in the current input shapefile and insert it into the output shapefile
                for row in search_cursor:
                    cursor.insertRow(row)

    print(f"Combined shapefiles saved to {output_shapefile}")


# A function to build the wellpad plots
def build_area_plot():

    # Create an output folder for the files
    output_folder = os.path.join(folder_loc, 'Working_Files', 'SHL_plots')

    # Check if the output folder exists; if not, create it
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # Add the combined sampled file in as the input file
    input_shapefile = folder_loc + r'\Working_Files\SHL_RanSamp_comb\Rand_SHL_comb.shp'
    output_shapefile = output_folder + r'\Sur_ranpad_100m.shp'


    # Create a buffer for the plots. 5.6419 makes a 100m2 circular plot
    buffer_distance = 5.6419
    # Perform buffer analysis
    arcpy.analysis.Buffer(
        in_features=input_shapefile,
        out_feature_class=output_shapefile,
        buffer_distance_or_field=buffer_distance,
        line_side="FULL",
        line_end_type="ROUND",
        dissolve_option="NONE",
        method="GEODESIC"
    )

    print ('Plots created.')


# Folder locations and files that you need to point to
folder_loc = (r'C:\BERA\00_Footprints_creation\Samples')
systematic_grid_shapefile = (folder_loc + r'\Source_files\Grid_15k_prj.shp')
ecosite_shapefile = (folder_loc + r'\Source_files\veg4_sur.shp')
original_lines = (folder_loc + r'\Source_files\Sur_2023_CL_ed.shp')
shl_shapefile = (folder_loc + r'\Source_files\Surmont_shl_2023_11_prj.shp')


setup_folders(folder_loc)

###Line sampling
get_orientation(original_lines)
add_ecosite(ecosite_shapefile, folder_loc + r'\Working_Files\Ecosite_polys')
clip_lines_by_ecosite(folder_loc + r'\Working_Files\Ecosite_polys', folder_loc + r'\Source_files\Sur_2023_CL_ed.shp', folder_loc + r'\Working_Files\Lines_ecosite')
create_strata(folder_loc + r'\Working_Files\Lines_ecosite', folder_loc + r'\Working_Files\Stratified_lines')
clip_all_lines(folder_loc + r'\Working_Files\Stratified_lines', systematic_grid_shapefile, folder_loc + r'\Working_Files\Grid_stratified_lines')
sample_all_lines(folder_loc + r'\Working_Files\Grid_stratified_lines')

#####Wellpad sampling
assign_ecosite_to_shl(shl_shapefile)
grid_shl_ecosites()
random_sample_shl()
combine_shapefiles()
build_area_plot()