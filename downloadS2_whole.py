# %% Run the following cell to initialize the API. The output will contain instructions on how to grant this notebook access to Earth Engine using your account.
# https://gorelick.medium.com/fast-er-downloads-a2abd512aa26
import ee
import geemap
import multiprocessing
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import norm, gamma, f, chi2
import pandas as pd
import IPython.display as disp
import json
import csv 
import os
import datetime
import requests
import shutil
from retry import retry
from datetime import datetime
from datetime import timedelta
import time
from osgeo import gdal
from multiprocessing import cpu_count
from multiprocessing.pool import ThreadPool
%matplotlib inline
ee.Authenticate()
ee.Initialize(opt_url='https://earthengine-highvolume.googleapis.com')
def ymdList(imgcol):
    def iter_func(image, newlist):
        date = ee.Number.parse(image.date().format("YYYYMMdd"));
        newlist = ee.List(newlist);
        return ee.List(newlist.add(date).sort())
    ymd = imgcol.iterate(iter_func, ee.List([]))
    return list(ee.List(ymd).reduce(ee.Reducer.frequencyHistogram()).getInfo().keys())
@retry(tries=10, delay=5, backoff=2)
def download_url(args):
    t0 = time.time()
    url = downloader(args[0],args[2])
    fn = args[1] 
    try:
        r = requests.get(url)
        with open(fn, 'wb') as f:
            f.write(r.content)
        return(url, time.time() - t0)
    except Exception as e:
        print('Exception in download_url():', e)
@retry(tries=10, delay=5, backoff=2)
def downloader(ee_object,region): 
    try:
        #download image
        if isinstance(ee_object, ee.image.Image):
            # print('Its Image')
            url = ee_object.getDownloadUrl({
                    'scale': 10, #463.831083333,
                    'crs': 'EPSG:4326',
                    'region': region,
                    'format': 'GEO_TIFF'
                })
            return url
        
        #download imagecollection
        elif isinstance(ee_object, ee.imagecollection.ImageCollection):
            print('Its ImageCollection')
            ee_object_new = ee_object.mosaic()
            url = ee_object_new.getDownloadUrl({
                    'scale': 10, #463.83108333310,
                    'crs': 'EPSG:4326',
                    'region': region,
                    'format': 'GEO_TIFF'
                })
            return url
    except:
        print("Could not download")
@retry(tries=10, delay=5, backoff=2)
def download_parallel(args):
    cpus = cpu_count()
    results = ThreadPool(cpus - 1).imap_unordered(download_url, args)
    for result in results:
        print('url:', result[0], 'time (s):', result[1])
t0 = time.time()
from datetime import datetime
from time import mktime

# meteor_path =  '/Users/joshuadimasaka/Desktop/PhD/GitHub/riskaudit/data/groundtruth/METEOR_PROJECT_2002'       
output_path = '/Users/joshuadimasaka/Desktop/PhD/GitHub/rwa'

# country_list = os.listdir(meteor_path); country_list.sort()
# if '.DS_Store' in country_list: country_list.remove('.DS_Store')
# %%
def add_cloud_bands(img):
    # Get s2cloudless image, subset the probability band.
    cld_prb = ee.Image(img.get('s2cloudless')).select('probability')

    # Condition s2cloudless by the probability threshold value.
    is_cloud = cld_prb.gt(CLD_PRB_THRESH).rename('clouds')

    # Add the cloud probability layer and cloud mask as image bands.
    return img.addBands(ee.Image([cld_prb, is_cloud]))

def add_shadow_bands(img):
    # Identify water pixels from the SCL band.
    not_water = img.select('SCL').neq(6)

    # Identify dark NIR pixels that are not water (potential cloud shadow pixels).
    SR_BAND_SCALE = 1e4
    dark_pixels = img.select('B8').lt(NIR_DRK_THRESH*SR_BAND_SCALE).multiply(not_water).rename('dark_pixels')

    # Determine the direction to project cloud shadow from clouds (assumes UTM projection).
    shadow_azimuth = ee.Number(90).subtract(ee.Number(img.get('MEAN_SOLAR_AZIMUTH_ANGLE')));

    # Project shadows from clouds for the distance specified by the CLD_PRJ_DIST input.
    cld_proj = (img.select('clouds').directionalDistanceTransform(shadow_azimuth, CLD_PRJ_DIST*10)
        .reproject(**{'crs': img.select(0).projection(), 'scale': 100})
        .select('distance')
        .mask()
        .rename('cloud_transform'))

    # Identify the intersection of dark pixels with cloud shadow projection.
    shadows = cld_proj.multiply(dark_pixels).rename('shadows')

    # Add dark pixels, cloud projection, and identified shadows as image bands.
    return img.addBands(ee.Image([dark_pixels, cld_proj, shadows]))

def add_cld_shdw_mask(img):
    # Add cloud component bands.
    img_cloud = add_cloud_bands(img)

    # Add cloud shadow component bands.
    img_cloud_shadow = add_shadow_bands(img_cloud)

    # Combine cloud and shadow mask, set cloud and shadow as value 1, else 0.
    is_cld_shdw = img_cloud_shadow.select('clouds').add(img_cloud_shadow.select('shadows')).gt(0)

    # Remove small cloud-shadow patches and dilate remaining pixels by BUFFER input.
    # 20 m scale is for speed, and assumes clouds don't require 10 m precision.
    is_cld_shdw = (is_cld_shdw.focalMin(2).focalMax(BUFFER*2/20)
        .reproject(**{'crs': img.select([0]).projection(), 'scale': 20})
        .rename('cloudmask'))

    # Add the final cloud-shadow mask to the image.
    return img_cloud_shadow.addBands(is_cld_shdw)

# Import the folium library.
import folium

# Define a method for displaying Earth Engine image tiles to a folium map.
def add_ee_layer(self, ee_image_object, vis_params, name, show=True, opacity=1, min_zoom=0):
    map_id_dict = ee.Image(ee_image_object).getMapId(vis_params)
    folium.raster_layers.TileLayer(
        tiles=map_id_dict['tile_fetcher'].url_format,
        attr='Map Data &copy; <a href="https://earthengine.google.com/">Google Earth Engine</a>',
        name=name,
        show=show,
        opacity=opacity,
        min_zoom=min_zoom,
        overlay=True,
        control=True
        ).add_to(self)

# Add the Earth Engine layer method to folium.
folium.Map.add_ee_layer = add_ee_layer

def display_cloud_layers(col):
    # Mosaic the image collection.
    img = col.mosaic()

    # Subset layers and prepare them for display.
    clouds = img.select('clouds').selfMask()
    shadows = img.select('shadows').selfMask()
    dark_pixels = img.select('dark_pixels').selfMask()
    probability = img.select('probability')
    cloudmask = img.select('cloudmask').selfMask()
    cloud_transform = img.select('cloud_transform')

    # Create a folium map object.
    center = AOI.centroid(10).coordinates().reverse().getInfo()
    m = folium.Map(location=center, zoom_start=12)

    # Add layers to the folium map.
    m.add_ee_layer(img,
                   {'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 2500, 'gamma': 1.1},
                   'S2 image', True, 1, 9)
    m.add_ee_layer(probability,
                   {'min': 0, 'max': 100},
                   'probability (cloud)', False, 1, 9)
    m.add_ee_layer(clouds,
                   {'palette': 'e056fd'},
                   'clouds', False, 1, 9)
    m.add_ee_layer(cloud_transform,
                   {'min': 0, 'max': 1, 'palette': ['white', 'black']},
                   'cloud_transform', False, 1, 9)
    m.add_ee_layer(dark_pixels,
                   {'palette': 'orange'},
                   'dark_pixels', False, 1, 9)
    m.add_ee_layer(shadows, {'palette': 'yellow'},
                   'shadows', False, 1, 9)
    m.add_ee_layer(cloudmask, {'palette': 'orange'},
                   'cloudmask', True, 0.5, 9)

    # Add a layer control panel to the map.
    m.add_child(folium.LayerControl())

    # Display the map.
    display(m)

def apply_cld_shdw_mask(img):
    # Subset the cloudmask band and invert it so clouds/shadow are 0, else 1.
    not_cld_shdw = img.select('cloudmask').Not()

    # Subset reflectance bands and update their masks, return the result.
    return img.select('B.*').updateMask(not_cld_shdw)

# %%
# check for city name here: https://code.earthengine.google.com/?scriptPath=Examples:Datasets/FAO/FAO_GAUL_2015_level2_FeatureView
lsib = ee.FeatureCollection("FAO/GAUL/2015/level0");
fcollection = lsib.filterMetadata('ADM0_NAME','equals','Rwanda');
aoi = ee.Geometry.MultiPolygon(fcollection.getInfo()['features'][0]['geometry']['coordinates'])
Map = geemap.Map()
Map.addLayer(aoi)
Map
# %% get direction and orbit number
startDATE = ee.Date('2018-01-01')
endDATE = ee.Date('2023-12-31')
im_coll = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterBounds(aoi)
            .filterDate(startDATE,endDATE)
            .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', 60))
            .sort('system:time_start'))   
# %%
ymdlistvariable = ymdList(im_coll)
ymd_year = [el[:4] for el in ymdlistvariable]
uniq_year = list(map(int, list(set(ymd_year))))
uniq_year.sort()
uniq_year
# %%
result_path = '/Users/joshuadimasaka/Desktop/PhD/GitHub/rwa/data/S2'
# %%
for i in range(len(uniq_year)):
    if i != 0 and i!=4: 
        ims = []
        fns = []
        rgns = []

        print(i)
        print(uniq_year[i])
        uniq_year_selected = uniq_year[i]

        startDATE = ee.Date(str(uniq_year[i]) + '-01-01')
        endDATE = ee.Date(str(uniq_year[i]) + '-12-31')

        AOI = aoi
        CLOUD_FILTER = 60
        CLD_PRB_THRESH = 40
        NIR_DRK_THRESH = 0.15
        CLD_PRJ_DIST = 2
        BUFFER = 100
        im_selected = im_coll.filterDate(startDATE,endDATE)
        s2_cloudless_coll = (ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY')
                    .filterBounds(aoi)
                    .filterDate(startDATE, endDATE)
                    .sort('system:time_start'))   
        s2_sr_cld_col_eval = ee.ImageCollection(ee.Join.saveFirst('s2cloudless').apply(**{
                                            'primary': im_selected,
                                            'secondary': s2_cloudless_coll,
                                            'condition': ee.Filter.equals(**{
                                                'leftField': 'system:index',
                                                'rightField': 'system:index'
                                            })
                                        }))
        s2_sr_median = (s2_sr_cld_col_eval.map(add_cld_shdw_mask)
                            .map(apply_cld_shdw_mask)
                            .median())

        ims.append(s2_sr_median.select(['B4']).clip(aoi))
        ims.append(s2_sr_median.select(['B3']).clip(aoi))
        ims.append(s2_sr_median.select(['B2']).clip(aoi))
        ims.append(s2_sr_median.select(['B5']).clip(aoi))
        ims.append(s2_sr_median.select(['B6']).clip(aoi))
        ims.append(s2_sr_median.select(['B7']).clip(aoi))
        ims.append(s2_sr_median.select(['B8A']).clip(aoi))
        ims.append(s2_sr_median.select(['B8']).clip(aoi))
        ims.append(s2_sr_median.select(['B11']).clip(aoi))
        ims.append(s2_sr_median.select(['B12']).clip(aoi))

        fns.append(str(result_path+'/'+str(uniq_year[i])+"_R.tif"))
        fns.append(str(result_path+'/'+str(uniq_year[i])+"_G.tif"))
        fns.append(str(result_path+'/'+str(uniq_year[i])+"_B.tif"))
        fns.append(str(result_path+'/'+str(uniq_year[i])+"_B5_RED1.tif"))
        fns.append(str(result_path+'/'+str(uniq_year[i])+"_B6_RED2.tif"))
        fns.append(str(result_path+'/'+str(uniq_year[i])+"_B7_RED3.tif"))
        fns.append(str(result_path+'/'+str(uniq_year[i])+"_B8A_RED4.tif"))
        fns.append(str(result_path+'/'+str(uniq_year[i])+"_B8_NIR.tif"))
        fns.append(str(result_path+'/'+str(uniq_year[i])+"_B8_SWIR1.tif"))
        fns.append(str(result_path+'/'+str(uniq_year[i])+"_B8_SWIR2.tif"))

        rgns.append(aoi)
        rgns.append(aoi)
        rgns.append(aoi)
        rgns.append(aoi)
        rgns.append(aoi)
        rgns.append(aoi)
        rgns.append(aoi)
        rgns.append(aoi)
        rgns.append(aoi)
        rgns.append(aoi)


        for k in range(len(ims)):

            ims_selected = ims[k]
            im_new = []
            fn_new = []
            rgn_new = []

            nrow = 10
            ncol = 10
            fishnet = geemap.fishnet(aoi, rows=nrow, cols=ncol)
            nlist = fishnet.size().getInfo()

            for j in range(nlist):

                if not os.path.isfile(fns[k][:-4]+"_"+str(j+1)+"_of_"+str(nlist)+".tif") or (os.path.getsize(fns[k][:-4]+"_"+str(j+1)+"_of_"+str(nlist)+".tif")/(1<<10)) < 1:

                    a = fishnet.toList(nlist).get(j).getInfo()
                    im_new.append(ims_selected.clip(
                        ee.Geometry.Polygon(a['geometry']['coordinates'])))
                    fn_new.append(fns[k][:-4]+"_"+str(j+1)+"_of_"+str(nlist)+".tif")
                    rgn_new.append(ee.Geometry.Polygon(a['geometry']['coordinates']))
            

            if len(im_new) != 0:
                download_parallel(zip(im_new, fn_new, rgn_new))
# %%
