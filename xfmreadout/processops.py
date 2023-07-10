import os
import re
import numpy as np
import periodictable as pt
from PIL import Image
from math import sqrt

import xfmreadout.clustering as clustering
import xfmreadout.utils as utils
import xfmreadout.imgops as imgops

FORCE = True
AUTOSAVE = True

EMBED_DIRNAME = "embedding"

#IGNORE_LINES=['sum','Back','Compton','Mo','MoL']
IGNORE_LINES=['Ar']
CUSTOM_LINES=['sum','Back','Compton']
Z_CUTOFFS=[11, 55, 37, 73]       #K min, K max, L min, M min

MODIFY_LIST = ['Na', 'Mg', 'Al', 'Si', 'Cl', 'sum', 'Back', 'Mo', 'MoL', 'Compton', 'S']
MODIFY_NORMS = [ 0.005, 0.01, 0.025, 0.1, 0.1, 0.5, 0.5, 0.5, 0.5, 0.5, 1.0 ]
BASEFACTOR=1/10000 #ppm to wt%

def get_elements(files):
    """

    Extract element names and corresponding files

    Ignore files that do not correspond to elements

    """
    elements=[]
    possible_lines = []
    keepfiles=[]    

    #use the periodic table and known z-cutoffs to get possible lines
    for ptelement in pt.elements:
        #add three versions of the line: K (unlabelled), L, M
        if ptelement.number >= Z_CUTOFFS[0] and ptelement.number <= Z_CUTOFFS[1]:
            possible_lines.append(ptelement.symbol)
        if ptelement.number >= Z_CUTOFFS[2]:
            possible_lines.append(ptelement.symbol+"L")
        if ptelement.number >= Z_CUTOFFS[3]:            
            possible_lines.append(ptelement.symbol+"M")

    for line in CUSTOM_LINES:
        possible_lines.append(line)

    for fname in files:
        try:
            found=re.search('\-(\w+)\.', fname).group(1)
        except AttributeError:
            print(f"WARNING: no element found in {fname}")
            found=''
        finally:
            if found == "var":
                pass
            elif found in IGNORE_LINES:
                pass
            elif found in possible_lines:
                elements.append(found)
                keepfiles.append(fname)
            else:
               print(f"WARNING: Unexpected element {found} not used")

    files = keepfiles
    if len(elements) == len(files):
        zipped = zip(elements, files)    
        zipped_sorted = sorted(zipped)

        elements = [elements for elements, files  in zipped_sorted]
        files = [files for elements, files in zipped_sorted]

    else:
        raise ValueError("mismatch between elements and files")

    return elements, files

def get_variance_files(elements, files):
    """
    search for variance sidecar files in filelist

    return list of variance files, with order matching elements

    raise an error if one is missing
    """

    variance_files = []

    variance_present = False

    for fname in files:
        try:
            symbol=re.search('\-(\w+)-var\.', fname).group(1)
        except AttributeError:
            symbol=''
        if symbol != '':
            variance_present = True
            break

    if variance_present:

        for element in elements:

            found_variance = False

            for fname in files:
                try:
                    symbol=re.search('\-(\w+)-var\.', fname).group(1)
                except AttributeError:
                    symbol=''

                if symbol == element:
                    variance_files.append(fname)
                    found_variance = True
                    break

            if found_variance == False:
                raise FileNotFoundError(f"No variance found for element {element}")

    return variance_files

def maps_load(filepaths):
    """
    load maps from datafiles, cleanup and reshape

    return dataset and dimensions
    """    

    #load an image and check dimensions
    im = Image.open(filepaths[0])
    img = np.array(im)

    dims = img.shape

    maps=np.zeros((dims[0], dims[1], len(filepaths)), dtype=np.float32)

    i=0
    for f in filepaths:
            im = Image.open(f)
            img = np.array(im)
            #replace all negative values with 0
            img = np.where(img<0, 0, img)
            if not (img.shape == dims):
                raise ValueError(f"unexpected dimensions for file {f}")
            maps[:,:,i]=img
            i+=1

    print(f"Initial shape: {maps.shape}")

    return maps

def maps_cleanup(maps):
    """
    discard empty rows at end of map
    """
    empty_begin=0
    empty_last=0
    for i in range(maps.shape[0]):
        row_maxcounts=np.max(maps[i,:,:])
        if row_maxcounts == 0:
            if empty_begin == 0:
                empty_begin=i
                empty_last=i
                print(f"WARNING: found empty row at {i} of {maps.shape[0]-1}")
            elif empty_last == (i-1):
                empty_last = i
            else:
                empty_last = i
                print(f"WARNING: DISCONTIGUOUS EMPTY ROW at {i}")

    maps=maps[0:empty_begin,:,:]
    print(f"Revised shape: {maps.shape}")

    return maps


def data_normalise(data, elements):
    """
    attempt to normalise data in absence of variance stats
    
    using pre-set list of approx. normalisation factors

    likely requires hand-tuning for each map
    """
    #iterate through all elements
    for i in range(data.shape[1]):
        factor=BASEFACTOR

        #check if element in MODIFY_LIST
        #   then norm to MODIFY_FACTOR
        for idx, sname in enumerate(MODIFY_LIST):
            if elements[i] == sname:
                factor=MODIFY_NORMS[idx]/np.max(data[:,i])
                print(f"--- scaling {sname} to {MODIFY_NORMS[idx]}")

        data[:,i]=(data[:,i]*factor)

    return data


def printqvals(data, element, qval):
        avg_data = np.average(data)
        max_data = np.max(data)
        qmean = utils.mean_within_quantile(data, qmin=qval)
        qnum = np.quantile(data,qval)

        print(f"{element} -- data: {avg_data:.3f}, data(max): {max_data:.3f}, qmean: {qmean:.3f}, qnum: {qnum:.3f}")

        return

def printsdvals(data, element, qval):
        avg_data = np.average(data)
        max_data = np.max(data)
        qmean = utils.mean_within_quantile(data, qmin=qval-0.25, qmax=qval)
        qnum = np.quantile(data,qval)

        print(f"{element} -- sd: {avg_data:.3f}, sd(max): {max_data:.3f}, qmean: {qmean:.3f}, qnum: {qnum:.3f}")

        return


def calc_quantiles(data, sd, multiplier):
    DATA_QUANTILE=0.999
    SD_QUANTILE_MIN=0.25
    SD_QUANTILE_MAX=0.5

    max_data = np.max(data)
    q99_data = utils.mean_within_quantile(data, qmin=DATA_QUANTILE)

    q2_sd = utils.mean_within_quantile(sd, qmin=SD_QUANTILE_MIN, qmax=SD_QUANTILE_MAX)

    ratio = q99_data / (q2_sd*multiplier)

    ratio = (q2_sd*multiplier) / q99_data

    return ratio, q99_data, q2_sd


def data_normalise_to_sd(data, sd, dims, elements):
    """
    normalise data against standard deviation
    
    use ratio of average_sd * 2 : average_conc
    divide by ratio if < 1
    """
    SD_MULTIPLIER = 2
    DEWEIGHT_FACTOR = 1
    DIRECT_MAPS = ["Compton", "sum", "Back", "Mo"]

    print("data0",data[:,0].shape)
    print("datafull",data.shape)    

    result = np.ndarray(data.shape, dtype=np.float32)
    result_sd = np.ndarray(sd.shape, dtype=np.float32)

    #iterate through all elements
    for i in range(data.shape[1]):
        
        data__ = np.copy(data[:,i])
        sd__ = np.copy(sd[:,i])

        ratio, q2_sd, q99_data = calc_quantiles(data__, sd__, SD_MULTIPLIER)

        print(f"{elements[i]} -- dataq99: {q99_data:.3f}, sdq2: {q2_sd:.3f}, max: {np.max(data__):.3f}")

        j=0
        while ratio >= 1:
            print(f"Gaussian averaging, cycle {j} -- dataq99: {q99_data:.3f}, sdq2: {q2_sd:.3f}, ratio: {ratio:.3f}")
            data__, sd__ = imgops.apply_gaussianblur(data__, sd__, dims, 1)

            #deweight element for each gaussian applied
            data__ = data__/DEWEIGHT_FACTOR
            sd__ = sd__/DEWEIGHT_FACTOR

            ratio, q2_sd, q99_data = calc_quantiles(data__, sd__, SD_MULTIPLIER)
            j+=1

        result[:,i] = data__
        result_sd[:,i] = sd__

#        print(f"{elements[i]} -- data: {avg_data:.3f}, data(98): {q99_data:.3f}, , data(max): {max_data:.3f}, ratio: {ratio:.3f}")
#        print(f"{elements[i]} -- sd: {avg_sd:.3f}, sd(25): {np.quantile(sd[:,i],0.25):.3f}, sd(max): {np.max(sd[:,i]):.3f}, sd(min): {np.min(sd[:,i]):.3f}, ratio: {ratio:.3f}")
        #result[:,i] = data[:,i]-q10_sd
        """
        TO DO:
            for each map:
                while ratio of sd to data above threshold
                   apply gaussian blur, improve sd
        """
        
        if False:
            subtracted = data[:,i]-q10_sd
            result[:,i] = subtracted.clip(0)

        if False:   #alternate method
            ratio=avg_sd*SD_MULTIPLE/avg_data   #default            
            if elements[i] not in DIRECT_MAPS:
                #result[:,i] = data[:,i]-q10_sd
                if ratio >= 1:
                    result[:,i] = data[:,i]/ratio
                else:
                    result[:,i] = data[:,i]
                result[:,i] = np.where(result[:,i]<0, 0, result[:,i])
            else:
                result[:,i] = data[:,i]/np.max(data[:,i])

    return result, result_sd


def variance_to_std(data):
    """
    convert variance stats to standard deviations via sqrt
    """
    result = np.sqrt(data)
    return result

def ppm_to_wt(data):
    """
    convert from ppm (as-read) to wt% 
    """
    result = data*BASEFACTOR
    return result

def data_crop(data, dims, x_min=0, x_max=9999, y_min=0, y_max=9999):
    """
    crop map to designated size
    """     
    maps = utils.map_roll(data, dims)

    print(f"Pre-crop shape: {maps.shape}")

    maps=maps[y_min:y_max,x_min:x_max,:]        #will likely fail if default out of range

    dims=maps[:,:,0].shape

    print(f"Cropped shape: {maps.shape}")

    ret_data, ret_dims = utils.map_unroll(maps)

    return ret_data, ret_dims

def calc_weights(data, weights, do_sqrt=True):
    if not weights.shape[0] == data.shape[1]:
        raise ValueError(f"shape mistmatch between weights {weights.shape} and data {data.shape}")

    for i in range(data.shape[1]):
        max_ = np.max(data[:,i])
        if do_sqrt:
            weights[i] = weights[i]*sqrt(max_)/max_
        else:
            weights[i] = weights[i]
        
    return weights

def apply_weights(data, weights):
    result = np.zeros(data.shape)

    for i in range(data.shape[1]):
        result[:,i] = data[:,i]*weights[i]
    
    return result

def extract_data(image_directory, files, is_variance=False):
    """
    get data from list of tiffs

    kwarg to specify whether reading variance or maps
    """

    filepaths = [os.path.join(image_directory, file) for file in files ] 

    maps = maps_load(filepaths)

    maps = maps_cleanup(maps)

    data, dims = utils.map_unroll(maps)

    print("-----")

    return data, dims

def compile(image_directory):
    """
    read tiffs from image directory 
    
    return corrected 2D stack, array of elements, and dimensions
    """

    print("-----------------")
    print("BEGIN reading processed data")
    print(f"Location: {image_directory}")
    print("-----")

    files_all = [f for f in os.listdir(image_directory) if f.endswith('.tiff')]

    elements, files_maps = get_elements(files_all)

    files_variance = get_variance_files(elements, files_all)
    
    if files_variance != []:
        variance_found = True

    print(f"Map files found: {len(files_maps)}")
    print(f"Elements identified: {elements}")

    if len(files_maps) != len(files_variance):
        raise ValueError("Mismatch between map and variance files")

    print("-----------------")    
    print(f"READING MAP DATA")
    data, dims = extract_data(image_directory, files_maps)
    data = ppm_to_wt(data)

    if variance_found:
        print("-----------------")
        print(f"READING VARIANCE DATA")
        var_data, var_dims = extract_data(image_directory, files_variance, is_variance=True)

        var_scale = dims[0] / var_dims[0]
        if not var_scale == (dims[1] / var_dims[1]):
            raise ValueError(f"inconsistent scale factor between x and y, for {dims} vs {var_dims} ")
        
        var_data, var_dims = imgops.data_resize(var_data, var_dims, var_scale)

        if not dims == var_dims:
            raise ValueError(f"mismatch between dimensions of data and rescaled variance, {dims} vs {var_dims} ")

        sd_data = variance_to_std(var_data)
        sd_data = ppm_to_wt(sd_data)
        sd_dims = var_dims

        data, sd_data = data_normalise_to_sd(data, sd_data, dims, elements)
    else:
        data = data_normalise(data, elements)

    print("-----------------")
    print(f"Final shape: {data.shape}")

    print("-----------------")
    print(f"Element values:")    
    for i in range(len(elements)):
        print(f"{elements[i]}, max: {np.max(data[:,i]):.2f}, 98: {np.quantile(data[:,i],0.98):.2f}, avg: {np.average(data[:,i]):.2f}")
    print("-----------------")


    return elements, data, dims, sd_data, sd_dims
