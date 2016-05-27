
'''
    distribute regional statistic by land use and area
    inputs:
        region shapefile with metrics
        land-use raster
        scaling factors

        given a raster cell, find all polygons that overlap (spatial index?)
        get the percentage coverage of each land use type
        based on inputed parameters
'''

import fiona
import rasterstats
import ConfigParser
import sys, os
from itertools import repeat
from shapely.geometry import shape
import numpy as np

#CASE WHEN OBJART  = 'AX_Wohnbauflaeche' THEN 1
#	WHEN OBJART  =  'AX_FlaecheBesondererFunktionalerPraegung' THEN 2
#	WHEN OBJART  = 'AX_FlaecheGemischterNutzung' THEN 3
#	WHEN OBJART  =  'AX_IndustrieUndGewerbeflaeche' THEN 4
#	ELSE 0
# END
values = ["remainder",
 'AX_Wohnbauflaeche',
 'AX_FlaecheBesondererFunktionalerPraegung',
 'AX_FlaecheGemischterNutzung',
 'AX_IndustrieUndGewerbeflaeche',
 'AX_SportFreizeitUndErholungsflaeche']

#land_use_categories: (band, name)

def calculate_region_land_use(region_shapefile, output_shapefile, land_use_raster_single_band, land_use_categories):
    with fiona.open(region_shapefile, 'r') as region_shapes:
        #for (band, lu_category) in land_use_categories:
        #    zs = rasterstats.zonal_stats(region_shapefile, land_use_raster,
        #                                      band = band, stats=['sum'])

        zs = rasterstats.zonal_stats(region_shapefile, land_use_raster_single_band,
                                            categorical=True, category_map=land_use_categories, geojson_out=True)

        print zs[1]

        schema = {'geometry': 'Polygon',
                'properties': [ ('AGS_Int', 'int'), ('GEN', 'str'), ('Area', 'float'), ('Area_covered', 'float')]}

        #create land use properties for new schema (will be percentages)
        land_use_properties = zip(zip(*land_use_categories)[1], repeat('float'))
        print land_use_properties
        schema['properties'].extend(land_use_properties)

        print schema

        with fiona.open(
         output_shapefile, 'w',
         driver=region_shapes.driver,
         crs=region_shapes.crs,
         schema=schema) as c:
                for region in zs:
                    old_properties = region['properties']

                    new_properties = {
                        'GEN': old_properties['GEN'],
                        'Area': old_properties['Shape_Area'],
                        'AGS_Int': old_properties['AGS_Int'],
                    }

                    total_land_used = sum([old_properties[key]
                                           for key in land_use_categories
                                           if key[0] != 0 and key in old_properties])
                    print total_land_used
                    for (k,cat_name) in land_use_categories:
                        if (k, cat_name) in old_properties and k != 0:
                            value = float(old_properties[(k,cat_name)]) / total_land_used
                            new_properties[cat_name] = value
                            print "\t", old_properties[(k,cat_name)] ,"\t", value
                        else:
                            new_properties[cat_name] = 0

                    new_properties['Area_covered'] = total_land_used*100
                    new_properties['Remainder'] = new_properties['Area'] - new_properties['Area_covered']

                    region['properties'] = new_properties

                    c.write(region)


#given a land_use array + transformation, mapping from region to land-uses and values, bounds of new array,

# {region : {key : value} }
import math
import rasterio
def distribute_region_statistics(land_use_raster_file, region_raster_file, region_shapefile):
    with rasterio.open(land_use_raster_file, 'r') as land_use_raster:
        with rasterio.open(region_raster_file, 'r') as region_raster:
            with fiona.open(region_shapefile, 'r'):


                affine_fine = land_use_raster.profile['affine']
                height = land_use_raster.profile['height']
                width = land_use_raster.profile['width']
                profile = land_use_raster.profile

                lu_array = land_use_raster.read()

                #move the bands to the third dimension to make calculations easier to read
                lu_array_bands_last = np.rollaxis(lu_array, 0, 3)
                print lu_array_bands_last.shape

                #remove remaining column
                REMAINDER_COL = 0
                lu_without_remainder = np.delete(lu_array_bands_last,REMAINDER_COL, axis=2)
                #expand summed area value so that the divison against each band will work
                lu_agg = lu_without_remainder.astype(float) / np.atleast_3d(np.sum(lu_without_remainder, axis=2))

                for (y,x,z), v in np.ndenumerate(lu_agg):
                    total_cell_land_use = v
                    if not math.isnan(v):
                        print (y,x), z, total_cell_land_use







#distribute_region_statistics("../../output/land_use_100m.tif", None)




def run_calculate_region_land_use():

    Config = ConfigParser.ConfigParser(allow_no_value=True)

    if len(sys.argv) == 1 or not os.path.exists(sys.argv[1]):
        raise IOError("please supply a configuration file as a program arugment")
    Config.read(sys.argv[1])

    cmap = [(float(k), v) for k,v in
                [tuple(Config.get("Class Values", c).split(',')) for c in Config.options("Class Values")]
            ]

    print cmap

    calculate_region_land_use("../../data/regional/Auspendler_in_Kernregion_25Proz_geglaettet",
                              "../../output/regions_with_land_use",
                              "../../data/land_use/land_use_merged_10m.tif", cmap)


run_calculate_region_land_use()


#
# for each 'zone building block', provide a scaling factor for that block
#
# for each municipality:
#   tablulate the m^2 coverage of each land use type
#   store total land use coverage (m^2) for that municipality
#
# create building blocks (at minimum resolution), and split at municipality regions
# link building blocks as children of a municipality
#
# for each building block:
#   get m^2 for each land use type
#   disaggregation factor is (raster_land_use / municipality_land_use)
#
# using config scaling factors, distribute population accordingly


# ????possibly use detailed population data to determine scaling factors?



