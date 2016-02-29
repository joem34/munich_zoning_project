import numpy
import os
from osgeo import ogr, osr
import psycopg2
import octtree

def loadboundaries(shapefile, baseSpatialRef):

    driver = ogr.GetDriverByName("ESRI Shapefile")
    # load shapefile
    dataSource = driver.Open(shapefile, 0)

    layer = load_layer_from_shapefile(dataSource)
    feature = layer.GetFeature(0)
    geom = feature.GetGeometryRef().Clone()

    #convert to EPSG:3035
    outSpatialRef = osr.SpatialReference()
    outSpatialRef.ImportFromEPSG(baseSpatialRef)

    geom.TransformTo(outSpatialRef)

    return geom

def load_layer_from_shapefile(dataSource):

    if dataSource is None:
        print 'Could not open %s' % (dataSource.GetName())
        return None
    else:
        print 'Opened %s' % (dataSource.GetName())
        layer = dataSource.GetLayer()

        featureCount = layer.GetFeatureCount()
        fieldCount = layer.GetLayerDefn().GetFieldCount()
        print "Number of features: %d, Number of fields: %d" % (featureCount, fieldCount)
        return layer


#Round up to next higher power of 2 (return x if it's already a power of 2).
#from http://stackoverflow.com/questions/1322510
def next_power_of_2(n):
    """
    Return next power of 2 greater than or equal to n
    """
    return 2**(n-1).bit_length()

def solve_iteratively(Config, pop_array, (x_min, y_min), resolution, boundary):
    ##
    # if num zones is too large, we need a higher threshold
    # keep a record of the thresholds that result in the nearest low, and nearest high
    # for the next step, take the halfway number between the two

    desired_num_zones = Config.getint("Parameters", "population_threshold")
    best_low = Config.getint("Parameters", "lower_population_threshold")
    best_high = Config.getint("Parameters", "upper_population_threshold")
    tolerance =  Config.getfloat("Parameters", "tolerance")

    step = 1
    solved = False
    num_zones = 0
    #TODO: flag to choose whether to include empty zones in counting, and when saving?

    pop_threshold = (best_high - best_low) / 2


    while not solved: # difference greater than 10%
        result_octtree = octtree.build(pop_array, (x_min, y_min), resolution, pop_threshold)
        print 'step %d with threshold level %d' % (step, pop_threshold)
        print "\toriginal number of cells:", result_octtree.count()
        num_zones = result_octtree.prune(boundary)
        print "\tafter pruning to boundary:", num_zones
        print ''


        solved = abs(num_zones - desired_num_zones)/float(desired_num_zones) < tolerance
        if not solved:
            if num_zones > desired_num_zones:
                best_low = max (best_low, pop_threshold)
            else:
                best_high = min (best_high, pop_threshold)
            pop_threshold = (best_low + best_high) / 2

        step += 1

    print "Solution found!"
    print "\t%6d zones" % (num_zones)
    print "\t%6d threshold" % (pop_threshold)

    return result_octtree



def load_data(Config, array_origin_x, array_origin_y, size):

    database_string = Config.get("Input", "databaseString")
    if database_string:
        conn = psycopg2.connect(None, "arcgis", "postgres", "postgres")
    else:
        db = Config.get("Input", "database")
        user = Config.get("Input", "user")
        pw = Config.get("Input", "password")
        host = Config.get("Input", "host")

        conn = psycopg2.connect(database=db, user=user, password=pw, host=host)
    cursor = conn.cursor()

    sql = Config.get("Input", "sql")

    resolution = Config.getint("Input", "resolution")

    x_max = array_origin_x + size * resolution
    y_max = array_origin_y + size * resolution

    pop_array = numpy.zeros((size, size), dtype=numpy.int)

    #cursor.execute("SELECT x_mp_100m, y_mp_100m, \"Einwohner\" FROM public.muc_all_population;")
    #this metheod only works when total rows = ncols x nrows in database. (IE no missing values)
    print "parameters", (array_origin_x, x_max, array_origin_y, y_max)
    cursor.execute(sql, (array_origin_x, x_max, array_origin_y, y_max)) #xmin xmax, ymin, ymax in that order
    #ttes charhra
    for row in cursor:
        if row[2] > 0:
            x = (row[0] - array_origin_x) / resolution
            y = (row[1] - array_origin_y) / resolution
            pop_array[y,x] = row[2]
        #reference arrays by (row_no , col_no)
        #reference arrays by (   a_y,      a_x   )

    print numpy.sum(pop_array)

    return pop_array

def tabulate_intersection(zone_octtree, octtreeSaptialRef, shapefile, inSpatialEPSGRef, class_field):
    print "running intersection tabulation"
    driver = ogr.GetDriverByName("ESRI Shapefile")
    # load shapefile
    dataSource = driver.Open(shapefile, 0)
    layer = load_layer_from_shapefile(dataSource)

    #get all distinct class_field values
    features = [feature.Clone() for feature in layer]

    field_values = list({f.GetField(class_field)[:8] for f in features})

    #set value for each zones and class to zero
    zones = {node: {} for node in zone_octtree.iterate()}

    for z in zones.iterkeys():
        for c in field_values:
            zones[z][c] = 0

    for feature in features:
        poly_class = feature.GetField(class_field)[:8]
        poly = feature.GetGeometryRef().Clone()

        inSpatialRef = osr.SpatialReference()
        inSpatialRef.ImportFromEPSG(inSpatialEPSGRef) #Germany zone 4 for ALKIS data

        outSpatialRef = osr.SpatialReference()
        outSpatialRef.ImportFromEPSG(octtreeSaptialRef)
        transform = osr.CoordinateTransformation(inSpatialRef, outSpatialRef)
        poly.Transform(transform)

        matches = zone_octtree.find_matches(poly, poly_class)

        for (zone, (class_name, percentage)) in matches:
            #print zone.index, class_name, percentage
            zones[zone][class_name] += percentage

    return (field_values, zones)

def save_intersections(filename, intersections, field_values):
    driver = ogr.GetDriverByName("ESRI Shapefile")
    # create the data source
    data_source = driver.Open(filename, 1)

    layer = data_source.GetLayer()
    for f in field_values:
        layer.CreateField(ogr.FieldDefn(f, ogr.OFTReal))

    for zone, classes in intersections.iteritems():
        feature = layer.GetFeature(zone.index)
        for c, percentage in classes.iteritems():
            feature.SetField(c, percentage)

        layer.SetFeature(feature)


    #data_source.Destroy()

#split along region borders
