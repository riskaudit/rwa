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

output_path = '/Users/joshuadimasaka/Desktop/PhD/GitHub/rwa'

# country_list = os.listdir(meteor_path); country_list.sort()
# if '.DS_Store' in country_list: country_list.remove('.DS_Store')

# %%
# custom_list = [5] #, 29, 30, 42]
# %%
# for ic in range(len(custom_list)):  #range(len(country_list)): 
    # %%
ims = []
fns = []
rgns = []
# icountry = country_list[custom_list[ic]]
# geoJSON_path = meteor_path + '/' + icountry + '/whole/extents'
# filenamelist = os.listdir(geoJSON_path); filenamelist.sort()
# if '.DS_Store' in filenamelist: filenamelist.remove('.DS_Store')
# %%
# for ifilename in range(len(filenamelist)): # range(custom start index,len(filenamelist)):
    # %%
# filename = filenamelist[ifilename]
# result_path = output_path+'/'+icountry+'/'+filename[:-9]
# if not os.path.exists(result_path):
#     os.makedirs(result_path)

# print(filename)
# with open(geoJSON_path+'/'+filename) as fa:
#     geoJSON = json.load(fa)      
# coords = geoJSON['features'][0]['geometry']['coordinates']
# aoi = ee.Geometry.Polygon(coords)
# region = aoi.toGeoJSONString()

# check for city name here: https://code.earthengine.google.com/?scriptPath=Examples:Datasets/FAO/FAO_GAUL_2015_level2_FeatureView
lsib = ee.FeatureCollection("FAO/GAUL/2015/level0");
fcollection = lsib.filterMetadata('ADM0_NAME','equals','Rwanda');
aoi = ee.Geometry.MultiPolygon(fcollection.getInfo()['features'][0]['geometry']['coordinates'])
Map = geemap.Map()
Map.addLayer(aoi)
Map
# Map = geemap.Map()
# Map.addLayer(aoi)
# Map
# %% get direction and orbit number
startDATE = ee.Date('2015-01-01')
endDATE = ee.Date('2023-12-31')
im_coll1 = (ee.ImageCollection('COPERNICUS/S1_GRD_FLOAT')
            .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
            .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
            .filter(ee.Filter.eq('instrumentMode', 'IW'))
            .filterBounds(aoi)
            .filterDate(startDATE,endDATE)
            .sort('system:time_start'))
ymdlistvariable = ymdList(im_coll1)
ymd_year = [el[:4] for el in ymdlistvariable]
uniq_year = list(map(int, list(set(ymd_year))))
uniq_year.sort()
yr = []
# %%
for i in range(len(uniq_year)):
    startDATE = ee.Date(str(uniq_year[i]) + '-01-01')
    endDATE = ee.Date(str(uniq_year[i]) + '-12-31')
    # if not os.path.isfile(str(result_path+'/'+str(uniq_year[i])+"_VH.tif")) or not os.path.isfile(str(result_path+'/'+str(uniq_year[i])+"_VV.tif")) or (os.path.getsize(str(result_path+'/'+str(uniq_year[i])+"_VH.tif"))/(1<<10)) < 1 or (os.path.getsize(str(result_path+'/'+str(uniq_year[i])+"_VH.tif"))/(1<<10)) < 1:
    im1 = im_coll1.filterDate(startDATE,endDATE).select('VH').mean().clip(aoi)
    im2 = im_coll1.filterDate(startDATE,endDATE).select('VV').mean().clip(aoi)

    ims.append(im1)
    ims.append(im2)
    fns.append(str(output_path+'/'+str(uniq_year[i])+"_VH.tif"))
    fns.append(str(output_path+'/'+str(uniq_year[i])+"_VV.tif"))
    rgns.append(aoi)
    rgns.append(aoi)

    yr.append(uniq_year[i])
    yr.append(uniq_year[i])
# %%
for i in range(8,len(yr)):
    print(i)
    print(yr[i])
    ims_selected = ims[i]
    uniq_year_selected = yr[i]
    nrow = 7
    ncol = 7
    fishnet = geemap.fishnet(aoi, rows=nrow, cols=ncol)
    nlist = fishnet.size().getInfo()

    im_new = []
    fn_new = []
    rgn_new = []

    if i != 14 and i != 15: 
        for j in range(nlist):

            if not os.path.isfile(fns[i][:-4]+"_"+str(j+1)+"_of_"+str(nlist)+".tif") or (os.path.getsize(fns[i][:-4]+"_"+str(j+1)+"_of_"+str(nlist)+".tif")/(1<<10)) < 1 or not os.path.isfile(fns[i][:-4]+"_"+str(j+1)+"_of_"+str(nlist)+".tif") or (os.path.getsize(fns[i][:-4]+"_"+str(j+1)+"_of_"+str(nlist)+".tif")/(1<<10)) < 1:

                a = fishnet.toList(nlist).get(j).getInfo()
                im_new.append(ims_selected.clip(
                    ee.Geometry.Polygon(a['geometry']['coordinates'])))
                fn_new.append(fns[i][:-4]+"_"+str(j+1)+"_of_"+str(nlist)+".tif")
                rgn_new.append(ee.Geometry.Polygon(a['geometry']['coordinates']))
        

    if len(im_new) != 0:
        download_parallel(zip(im_new, fn_new, rgn_new))
 


# %%
