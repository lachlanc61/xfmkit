import os
import numpy as np

import xfmreadout.bufferops as bufferops
import xfmreadout.dtops as dtops
import xfmreadout.utils as utils

#CLASSES
class Xfmap:
    """
    Object wrapping binary file to be read
        holds: params read directly from file
        loads: byte stream from file, holds pointer
        methods to parse pixel header and body, manage memory via chunks
            bufferops.py module contains subsidiary code to parse binary
    """
    def __init__(self, config, fi, fo, WRITE_MODIFIED: bool, CHUNK_SIZE: int, MULTIPROC: bool):

        #assign input file object for reading
        try:
            self.infile = open(fi, mode='rb') # rb = read binary
            if WRITE_MODIFIED:
                self.writing = True
                self.outfile = open(fo, mode='wb')   #wb = write binary
            else:
                self.writing = False
        except FileNotFoundError:
            print("FATAL: incorrect filepath/files not found")

        #get total size of file to parse
        self.fullsize = os.path.getsize(fi)
        self.chunksize = CHUNK_SIZE

        self.fidx=self.infile.tell()

        if self.fidx != 0:
            raise ValueError(f"File pointer at {self.fidx} - Expected 0 (start of file)")

        #read the beginning of the file into buffer
        buffer = bufferops.MapBuffer(self.infile, self.chunksize, MULTIPROC)

        #read the JSON header and store position of first pixel
        self.headerdict, self.datastart, buffer = bufferops.readjsonheader(buffer, 0)
        
        #try to assign values from header
        try:
            self.xres = int(self.headerdict['File Header']['Xres'])           #map size x
            self.yres = int(self.headerdict['File Header']['Yres'])           #map size y
            self.xdim = float(self.headerdict['File Header']['Width (mm)'])     #map dimension x
            self.ydim = float(self.headerdict['File Header']['Height (mm)'])    #map dimension y
            self.nchannels = int(self.headerdict['File Header']['Chan']) #no. channels
            self.gain = float(self.headerdict['File Header']['Gain (eV)']/1000) #gain in kV
            self.deadtime = float(self.headerdict['File Header']['Deadtime (%)'])
            self.dwell = float(self.headerdict['File Header']['Dwell (mS)'])   #dwell in ms
            self.timeconst = float(config['time_constant']) #pulled from config, ideally should be in header
        except:
            raise ValueError("FATAL: failure reading values from header")
               
        #initialise arrays
        self.chan = np.arange(0,self.nchannels)     #channel series
        self.energy = self.chan*self.gain           #energy series
        self.xarray = np.arange(0, self.xdim, self.xdim/self.xres )   #position series x  
        self.yarray = np.arange(0, self.ydim, self.ydim/self.yres )   #position series y
            #NB: real positions likely better represented by centres of pixels eg. 0+(xdim/xres), xdim-(xdim/xres) 
            #       need to ask IXRF how this is handled by Iridium

        #derived vars
        self.npx = self.xres*self.yres        #expected number of pixels
        self.dimensions = ( self.yres, self.xres )

        #config constants
        self.PXHEADERLEN=config['PXHEADERLEN'] 
        self.BYTESPERCHAN=config['BYTESPERCHAN'] 

        self.detarray = bufferops.getdetectors(buffer, self.datastart, self.PXHEADERLEN)
        self.ndet = max(self.detarray)+1

        self.indexlist=np.empty((self.npx, self.ndet),dtype=np.uint64)

        buffer.wait()
        self.resetfile()
        return

    def resetfile(self):
        self.infile.seek(0)

    def closefiles(self):
        self.infile.close()
        if self.writing:
            self.outfile.close()



class PixelSeries:
    def __init__(self, config, xfmap, npx, detarray, INDEX_ONLY: bool):

        #copied variables
        self.source=xfmap
        self.energy=xfmap.energy
        self.dimensions = xfmap.dimensions


        #assign number of detectors
        self.detarray = detarray
        self.npx = npx
        self.ndet=max(self.detarray)+1
        self.nchan=config['NCHAN']

        #initialise pixel value arrays
        self.parsed=False
        self.pxlen=np.zeros((npx,self.ndet),dtype=np.uint16)
        self.xidx=np.zeros((npx,self.ndet),dtype=np.uint16)
        self.yidx=np.zeros((npx,self.ndet),dtype=np.uint16)
        self.det=np.zeros((npx,self.ndet),dtype=np.uint16)
        self.dt=np.zeros((npx,self.ndet),dtype=np.float32)

        #initalise derived arrays
        #flat
        self.flattened=np.zeros((npx),dtype=np.uint32) 
        self.flatsum=np.zeros((npx),dtype=np.uint32) 
        self.dtflat=np.zeros((npx),dtype=np.float32)  
        #per-detector
        self.sum=np.zeros((npx,self.ndet),dtype=np.uint32)  
        self.dtmod=np.zeros((npx,self.ndet),dtype=np.float32)  

        #create analysis outputs
        self.rvals=np.zeros(npx)
        self.gvals=np.zeros(npx)
        self.bvals=np.zeros(npx)
        self.totalcounts=np.zeros(npx)

        #dummy arrays for outputs
        self.categories=np.zeros(10)
        self.classavg=np.zeros(10)
        self.rgbarray=np.zeros(10)      
        self.corrected=np.zeros(10)

        #initialise whole data containers (WARNING: large)
        if not INDEX_ONLY:
            self.data=np.zeros((npx,self.ndet,self.nchan),dtype=np.uint16)
#            if config['DOBG']: self.corrected=np.zeros((xfmap.npx,config['NCHAN']),dtype=np.uint16)
        else:
        #create a small dummy array just in case
            self.data=np.zeros((1024,self.nchan),dtype=np.uint16)

        self.parsing = INDEX_ONLY

        #self.nrows=0

    def receiveheader(self, pxidx, pxlen, xcoord, ycoord, det, dt):
        self.pxlen[pxidx,det]=pxlen
        self.xidx[pxidx,det]=xcoord
        self.yidx[pxidx,det]=ycoord
        self.det[pxidx,det]=det
        self.dt[pxidx,det]=dt
        
        return self

    def get_dtmod(self, config, xfmap, modify_dt: float):
            """
            calculate derived arrays from values extracted from map
            """
            #modify_dt used as both flag and value
            if modify_dt == -1:
                #dt = unchanged
                self.dtmod = self.dt
            elif modify_dt == 999:
                #dt = predicted
                self.dtmod = dtops.predict_dt(config, self, xfmap)
            elif modify_dt >= 0 and modify_dt <= 100:
                #dt = assigned value 0-100
                self.dtmod = np.full((self.dt.shape), np.float32(modify_dt), dtype=np.float32) 
            else:
                raise ValueError("unexpected value for modify_dt") 

            return self

    def get_derived(self):
        """
        calculate derived arrays from values extracted from map
        """
        self.flattened = np.sum(self.data, axis=1, dtype=np.uint32)
        self.sum = np.sum(self.data, axis=2, dtype=np.uint32)
        self.flatsum = np.sum(self.sum, axis=1, dtype=np.uint32)

        return self


    def flatten_REMOVE(self, data, detarray):
        """
        sum all detectors into single data array
        NB: i think this creates another dataset in memory while running
        PRETTY SURE NOT USED - confirm
        """
        flattened = data[0]
        if len(detarray) > 1:
            for i in detarray[1:]:
                flattened+=data[i]
        
        return flattened

    def exportpxstats(self, config, dir):
        """
        write the pixel header statistics
        """
        if config['SAVEFMT_READABLE']:
            for i in self.detarray:
                np.savetxt(os.path.join(dir, "pxstats_pxlen.txt"), self.pxlen, fmt='%i', delimiter=",")
                np.savetxt(os.path.join(dir, "pxstats_xidx.txt"), self.xidx, fmt='%i', delimiter=",")
                np.savetxt(os.path.join(dir, "pxstats_yidx.txt"), self.yidx, fmt='%i', delimiter=",")
                np.savetxt(os.path.join(dir, "pxstats_detector.txt"), self.det, fmt='%i', delimiter=",")
                np.savetxt(os.path.join(dir, "pxstats_dt.txt"), self.dt, fmt='%f', delimiter=",")    
                
                #include derived stats if data was fully parsed
                if self.parsing:
                    np.savetxt(os.path.join(dir, "pxstats_sum.txt"), self.sum, fmt='%d', delimiter=",")  
                    np.savetxt(os.path.join(dir, "pxstats_dtmod.txt"), self.dtmod, fmt='%d', delimiter=",")    
                    np.savetxt(os.path.join(dir, "pxstats_dtflat.txt"), self.dtflat, fmt='%d', delimiter=",")  
        else:
            np.save(os.path.join(dir, "pxstats_pxlen"), self.pxlen)            
            np.save(os.path.join(dir, "pxstats_xidx"), self.xidx)    
            np.save(os.path.join(dir, "pxstats_yidx"), self.yidx)     
            np.save(os.path.join(dir, "pxstats_det"), self.det)     
            np.save(os.path.join(dir, "pxstats_dt"), self.dt)

            if self.parsing:
                np.save(os.path.join(dir, "pxstats_sum"), self.sum)  
                np.save(os.path.join(dir, "pxstats_dtmod"), self.dtmod)    
                np.save(os.path.join(dir, "pxstats_dtflat"), self.dtflat) 



    def exportpxdata(self, config, dir):
        """
        writes the spectrum-by-pixel data to csv
        """
        if config['SAVEFMT_READABLE']:
            for i in self.detarray:
                np.savetxt(os.path.join(dir,  config['export_filename'] + f"{i}.txt"), self.data[i], fmt='%i')
        else:
            np.save(os.path.join(dir,  config['export_filename']), self.data)


    def importpxdata(self, config, dir):
        """
        read data from csv
            does not currently return as much information as the full parse

        NB: currently broken after refactor
        """
        print("loading from file", config['export_filename'])
        self.data = np.loadtxt(os.path.join(dir, config['outfile']), dtype=np.uint16, delimiter=",")
        self.pxlen=np.loadtxt(os.path.join(dir, "pxstats_pxlen.txt"), dtype=np.uint16, delimiter=",")
        self.xidx=np.loadtxt(os.path.join(dir, "pxstats_xidx.txt"), dtype=np.uint16, delimiter=",")
        self.yidx=np.loadtxt(os.path.join(dir, "pxstats_yidx.txt"), dtype=np.uint16, delimiter=",")
        self.det=np.loadtxt(os.path.join(dir, "pxstats_detector.txt"), dtype=np.uint16, delimiter=",")
        self.dt=np.loadtxt(os.path.join(dir, "pxstats_dt.txt"), dtype=np.float32, delimiter=",")
        
        print("loaded successfully", config['export_filename']) 

        return self


def data_unroll(maps):
    """
    reshape map (x, y, counts) to data (i, counts)

    returns dataset and dimensions
    """

    if len(maps.shape) == 3:
        data=maps.reshape(maps.shape[0]*maps.shape[1],-1)
        dims=maps.shape[:2]
    elif len(maps.shape) == 2:
        data=maps.reshape(maps.shape[0]*maps.shape[1])
        dims=maps.shape[:2]        
    else:
        raise ValueError(f"unexpected dimensions for {map}")

    return data, dims    




class DataSeries:
    def __init__(self, datastack, dimensions=None, labels=[] ):
        """
        linked pair of 1D dataset and 2D image stack that are views of each other
        """    
            
        self.data, self.dimensions = self.import_by_shape(datastack, dimensions=dimensions)

        #TO DO: check C-contiguous and copy to new dataset if not

        #check if labels are correct shape
        if not labels == []:
            self.labels = self.apply_labels(labels)
        else:
            self.labels= []
        
        #assign a 2D view for image-based operations
        self.mapview = self.data.reshape(dimensions[0], dimensions[1], -1)

        self.check()

    def check(self):
        """
        basic checks on dataset    
        """
        if not len(self.data.shape) == 2:
            raise ValueError("invalid data shape")
        
        if not len(self.mapview.shape) == 3:
            raise ValueError("invalid maps shape")
        
        if not self.data.shape[1] == self.mapview.shape[2]:
            raise ValueError("mismatch between data and map channels")
        
        if not self.data.shape[0] == self.mapview.shape[0]*self.mapview.shape[1]:
            raise ValueError("mismatch between data and map shapes")
        
        if not self.dimensions == (self.mapview.shape[0], self.mapview.shape[1]):
            raise ValueError("mismatch between specified dimensions and map shape")
        
        if not ( self.labels == [] or self.data.shape[1] == len(self.labels) ):
            raise ValueError("mismatch between data and label shapes")
        return

    def import_by_shape(self, datastack, dimensions=None):
        """
        ingest an array and extract data and dimensions

        array can be either 3D Y,X,NCHAN or 2D N, NCHAN

        unrolled dimensions must be given for 2D map   
        """

        #if 2D data and 2 dimensions given, proceed as N,CHAN map with explicit dims
        if len(dimensions) == 2 and len(datastack.shape) == 2:
            data_ = datastack
            dimensions_ = dimensions
        
        #if 3D data given with matching dimensions, proceed as Y,X,CHAN map with explicit dims
        elif len(datastack.shape) == 3 and dimensions == (self.datastack.shape[0], self.datastack.shape[1]):
            data_ = datastack.reshape(datastack.shape[0]*datastack.shape[1],-1)
            dimensions_ = dimensions

        #if 3D data given without dimensions, proceed as Y,X,CHAN map and derive dimensions
        elif dimensions == None and len(datastack.shape) == 3:
            dimensions_ = (datastack.shape[0], datastack.shape[1])
            data_ = datastack.reshape(datastack.shape[0]*datastack.shape[1],-1)

        #fail cases:
        elif dimensions == None and not len(datastack.shape) == 3:  
            raise ValueError("2D dataset provided without explicit map dimensions")          
        else:
            raise ValueError(f"Unexpected shapes for data {datastack.shape} and dimensions {dimensions}")

        return data_, dimensions_

    def apply_labels(self, labels):
        """
        check and apply a set of labels    
        """
        if len(labels) == self.data.shape[1]:
            self.labels = labels
        else:
            raise ValueError("Mismatch between label and data dimensions")
    
    def crop(self, xrange=(0, 9999), yrange=(0, 9999)):
        """
        crop maps in 2D and adjustcorresponding 1D view
        """
        self.maps = self.mapview[yrange[0]:yrange[1], xrange[0]:xrange[1], :]
        self.dimensions = (self.mapview.shape[0], self.mapview.shape[1])
        self.data = self.mapview.reshape(self.mapview.shape[0]*self.mapview.shape[1],-1)
        return self

#meta-class with set of DataSeries
class DataSet:
    def __init__(self, dataseries: DataSeries, se:DataSeries=None):
        self.d = dataseries
        self.dimensions = dataseries.dimensions

        if se == None:
           self.se = DataSeries(np.sqrt(dataseries.data), dataseries.dimensions) 
        else:
            self.se = se

        self.check()

    def check(self):
        if not self.d.data.shape == self.se.data.shape:
            raise ValueError("shape mismatch between data and serr")        
        
        if not self.d.dimensions == self.se.dimensions:
            raise ValueError("stored dimension mismatch between data and serr")  

    #  TO DO extend crop, zoom etc to crop data + errors

#meta-class with extended DataSeries
#data can be accessed directly as self.data, self.mapview etc
#error accessible next layer down as self.se.data
class DataStatsSeries(DataSeries):
    def __init__(self, datastack, dimensions=None, labels=[], se:np.ndarray=None ):
        
        #apply all attrs/methods from DataSeries
        super().__init__(datastack, dimensions=dimensions, labels=labels)
        
        #add errors as second, nested DataSeries
        if se == None:
            self.se = DataSeries(np.sqrt(self.data), self.dimensions) 
        elif se.shape == self.data.shape:
            self.se = DataSeries(se, self.dimensions) 
        else:
            raise ValueError("mismatch between data and stderror dimensions")
        print(self.data)

    #  TO DO must extend crop, zoom etc to crop error as well...
