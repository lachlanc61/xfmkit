import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as colors
import matplotlib.cm as cmx
import cv2
import os
import glob
import struct 
import time
from decimal import *
from scipy.optimize import curve_fit
from src.utils import *

#-----------------------------------
#USER MODIFIABLE VARIABLES
#-----------------------------------
#global variables
FTYPE=".GeoPIXE"    #valid: ".GeoPIXE"
DEBUG=False     #debug flag 
PXHEADERLEN=16  #pixel header size
PXFLAG="DP"
NCHAN=4096
CHARENCODE = 'utf-8'
MAPX=128
MAPY=68

#workdir and inputfile
wdirname='data'     #working directory relative to script
odirname='out'      #output directory relative to script
infile = "leaf2_overview.GeoPIXE"    #assign input file
                                #   only used if reading .geo

detid="A"

#figure params
colourmap='Set1'    #colourmap for figure
#colourmap='copper'    #colourmap for figure
figx=20         #cm width of figure
figy=10         #cm height of figure
smallfont = 8   #default small font
medfont = 10    #default medium font
lgfont = 12     #default large font
lwidth = 1  #default linewidth
bwidth = 1  #default border width


#-------------------------------------
#FUNCTIONS
#-----------------------------------


def binunpack(stream, idx, sformat):
    if sformat == "<H":
        nbytes=2
    elif sformat == "<f":
        nbytes=4
    elif sformat == "<I":
        nbytes=4
    else:
        print(f"ERROR: {sformat} not recognised by local function binunpack")
        exit(0)
#    frame=stream[idx:idx+nbytes]
#    print("frame", frame)
    retval = struct.unpack(sformat, stream[idx:idx+nbytes])[0]
    idx=idx+nbytes
    return(retval, idx)    

def readpxrecord(idx, stream):
    """"
    Pixel Record
    Note: not name/value pairs for file size reasons. The pixel record header is the only record type name/value pair, for easier processing. We are keeping separate records for separate detectors, since the deadtime information will also be per detector per pixel.
        1.	Record type pair  "DP", Length of pixel data record in bytes ( 4 byte int)
        2.	X                          Horizontal pixel index (2 byte int)
        3.	Y                          Vertical pixel index (2 byte int)
        4.	Detector               Data in this record is for this detector (2 byte int)
        5.	Deadtime             Deadtime for this pixel (4 byte float)
        6.	Data (for each channel with data up to maximum channel index)
            a.	Channel     Channel index (0- Max Chan) (2 byte int)
            b.	Count         Event counts in channel (2 byte int)

    #   concise format:
    #   DP  len     X       Y       det     dt  DATA
    #   2c  4i     2i       2i      2i      4f
    """
    #assign current position as start of px record
    pxstart=idx
    

#   check for pixel start flag "DP" at first position after header:
    #   unpack first two bytes after header as char
    pxflag=struct.unpack("cc", stream[idx:idx+2])[:]
    #   use join to merge into string
    pxflag="".join([pxflag[0].decode(CHARENCODE),pxflag[1].decode(CHARENCODE)])

    #   check if string is "DP" - if not, fail
    if pxflag != PXFLAG:
        print(f"ERROR: pixel flag 'DP' not found at byte {idx}")
        exit()
    else:
        print(f"found pixel at: {idx}")

    idx=idx+2   #step over "DP"

    #read each header field and step idx to end of field
    pxlen, idx=binunpack(stream,idx,"<I")
    xcoord, idx=binunpack(stream,idx,"<H")
    ycoord, idx=binunpack(stream,idx,"<H")
    det, idx=binunpack(stream,idx,"<H")
    dt, idx=binunpack(stream,idx,"<f")

    #print header fields
    if (DEBUG): 
        print(pxlen)
        print(xcoord)
        print(ycoord)
        print(det)
        print(dt)

    #initialise channel index and result arrays
    j=0
    chan=np.zeros(int((pxlen-PXHEADERLEN)/4), dtype=int)
    counts=np.zeros(int((pxlen-PXHEADERLEN)/4), dtype=int)
    #       4 = no. bytes in each x,y pair
    #         = 2x2 bytes each 

    #iterate until byte index passes pxlen
    #pull channel, count pairs
    while idx < (pxstart+pxlen):
    #while idx < 2000:
        chan[j], idx=binunpack(stream,idx,"<H")
        #chan[j]=int(chan[j])
        counts[j], idx=binunpack(stream,idx,"<H")
        if (DEBUG): print(idx,chan[j],counts[j])
        if (DEBUG): print(idx, pxstart+pxlen)
        j=j+1
    if (DEBUG): print(f"following bytes at {idx}: {stream[idx:idx+10]}")
    return(chan, counts, pxlen, xcoord, ycoord, det, dt, idx)

#-----------------------------------
#INITIALISE
#-----------------------------------

#initialise directories relative to script
script = os.path.realpath(__file__) #_file = current script
spath=os.path.dirname(script) 
wdir=os.path.join(spath,wdirname)
odir=os.path.join(spath,odirname)
print("script:", script)
print("script path:", spath)
print("data path:", wdir)
print("---------------")

#plot defaults
plt.rc('font', size=smallfont)          # controls default text sizes
plt.rc('axes', titlesize=smallfont)     # fontsize of the axes title
plt.rc('axes', labelsize=medfont)    # fontsize of the x and y labels
plt.rc('xtick', labelsize=smallfont)    # fontsize of the tick labels
plt.rc('ytick', labelsize=smallfont)    # fontsize of the tick labels
plt.rc('legend', fontsize=smallfont)    # legend fontsize
plt.rc('figure', titlesize=lgfont)  # fontsize of the figure title
plt.rc('lines', linewidth=lwidth)
plt.rcParams['axes.linewidth'] = bwidth


fig=plt.figure()
ax=fig.add_subplot(111)
ax.set_yscale('log')

ax.set_ylabel('intensity (counts)')
ax.set_xlim(0,25)

#ax.set_xscale('log')
ax.set_xlim(0,NCHAN/1.5)
ax.set_xlabel('energy (keV)')


starttime = time.time() #initialise timer
totalpx=MAPX*MAPY   # map size

#-----------------------------------
#MAIN START
#-----------------------------------
"""
Read binary with struct
https://stackoverflow.com/questions/8710456/reading-a-binary-file-with-python
Read binary as chunks
https://stackoverflow.com/questions/71978290/python-how-to-read-binary-file-by-chunks-and-specify-the-beginning-offset
"""


if FTYPE == ".GeoPIXE":
    f = os.path.join(wdir,infile)
    fname = os.path.splitext(os.path.basename(f))[0]

    print("opening .geo:",fname)
else: 
    print(f'FATAL: filetype {FTYPE} not recognised')
    exit()

print("---------------")

with open(f, mode='rb') as file: # rb = read binary
    
    stream = file.read()    #NB. to read in chunks, add chunk size as read(SIZE)
    streamlen=len(stream)
    print("stream length in bytes ",streamlen)

    print("first two bytes: ",stream[:2])

    #struct unpack outputs tuple, want int
    #get header length from first two bytes
    #   read as little-endian uint16 "<H"
    headerlen = int(struct.unpack("<H", stream[:2])[0])
    print(f"header length: {headerlen}")

    #occasionally, files might be missing the header
    #   when this happens, the first bytes are "DP" - denoting the start of a pixel record
    #   therefore if we get 20550 (="DP" as <uint16), header is missing
    if headerlen == 20550:
        print("WARNING: no header found")
        headerlen=0
    
    #assign starting index 
    idx=headerlen+2 #legnth of header + 2 bytes

    #initialise pixel param arrays
    pxlen=np.zeros(totalpx)
    xidx=np.zeros(totalpx)
    yidx=np.zeros(totalpx)
    det=np.zeros(totalpx)
    dt=np.zeros(totalpx)
    
    i=0 #pixel counter
    while idx < streamlen:
        #check index against expected map dimensions

        #read pixel record
        #   output spectrum, all header params, finishing index
        chan, counts, pxlen[i], xidx[i], yidx[i], det[i], dt[i], idx = readpxrecord(idx, stream)
        #fill gaps in spectrum 
        #   (ie. all chans where y=0 are missing, add them back)
        chan, counts = gapfill(chan,counts, NCHAN)

        if i > totalpx:
            print(f"WARNING: pixel count {i} exceeds expected map size {totalpx}")

        #pixel outputs:
#        ax.plot(chan, counts, color = "red", label=i)
#        print(chan[40:60], counts[40:60])
#        print("index at end of record",idx)

 #       if idx > 200000:
 #           print("ending at:", idx)
 #           idx=72222500
        i+=1

    print("---------------------------")
    print("MAP COMPLETE")
    print("---------------------------")
    #output result arrays   
    runtime = time.time() - starttime
    print("pixels expected (X*Y):", totalpx) 
    print("pixels found:", i)
    print(f"total time: {round(runtime,2)} s")
    print(f"time per pixel: {round((runtime/i),7)} s") 
    print("---------------------------")
    print("pixel lengths")
    print(pxlen[:i])
    print("xidx")
    print(xidx[:i])
    print("yidx")
    print(yidx[:i])
    print("detector")
    print(det[:i])
    print("dt")
    print(dt[:i])    
    #plotting

#    plt.show()

print("CLEAN EXIT")
exit()































success=True
steps=np.arange(10)
while success:
    #initialise plot and colourmaps per frame
    plt.rcParams["figure.figsize"] = [figx/2.54, figy/2.54]
    plt.rcParams["figure.figsize"] = [figx/2.54, figy/2.54]
    fig=plt.figure()
    lut = cm = plt.get_cmap(colourmap) 
    cNorm  = colors.Normalize(vmin=0, vmax=len(steps)+2)
    scalarMap = cmx.ScalarMappable(norm=cNorm, cmap=lut)

    #READ NEXT FRAME
    #filetype switcher again - read .avi and .tif differently
    #   paired with switcher at top of main 
    #   - be very careful that all branches send the same results downstream
    if FTYPE == ".GeoPIXE":
        #read a frame from the avi, returning success
        readimage = f

        if readimage is not None:
                success=True
        else:
            print("failed for",f)
            success=False
    else:
        print("FATAL: filetype {%} not recognised",FTYPE)
        exit()    

    print('Read frame : ', readimage)

    #leave loop if import unsuccessful (ie. no more frames)
    if not success:
        break
    
    exit()
print("CLEAN END")