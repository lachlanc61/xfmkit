# Overview

This tool parses spectrum-by-pixel maps from X-ray Flourescence Microscopy (XFM). It is currently compatible with ATLAS-series spectrometers from IXRF Inc. 

These instruments raster a high-energy X-ray beam across a specimen, detecting X-ray fluorescence from the material. The resulting dataset is a spectral cube containing an elemental fingerprint across the map. This data can be used to determine the composition of the material at each pixel. 

Analysis is manual and time-consuming, and there is a need for rapid, automated visualisation and class-averaging to inform the user's decision-making during the experiment.

This package performs dimensionality-reduction and clustering on XFM datasets, producing class-averages which aid in manual processing. It also produces a simple RGB visualisation weighted by spectral region, as an at-a-glance representation of these multidimensional datasets. 

# Summary:

- parses JSON/binary .GeoPIXE files

- extracts pixel records and pixel parameters

- projects spectra onto an RGB colourmap for rapid visualisation of the distribution of major phases

- performs dimensionality-reduction

- performs class-averaging, and exports these class averages for use in later processing

# Method

The instrument data format is a mixed JSON/binary with sparse pixel records:

<p align="left">
  <img src="./docs/IMG/fileformat4.png" alt="Spectrum" width="1024">
  <br />
</p>

- The JSON header is loaded as a dictionary, yielding map dimensions
    - (src.bitops.readgpxheader)
- Pixel records are parsed and loaded into a large 2D numpy array (shape = pixels * channels) 
    - (src.bitops.readpxrecord) 
    - Pixel parameters are extracted from the indidual pixel headers
- Any missing channel records are reintroduced as zeroes
    - (src.utils.gapfill)

#

Single-pixel spectra are mapped to RGB values using the HSV colourmap:
- Sum of: spectrum intensity * R G B channel values, across spectrum
    - (src.colour.spectorgb)

<p align="left">
  <img src="./docs/IMG/hsv_spectrum2.png" alt="Spectrum" width="700">
  <br />
</p>

- An x * y map is created from RGB-values per pixel:
    - (src.colour.complete) 

<p align="left">
  <img src="./docs/IMG/geo_colours2.png" alt="Spectrum" width="700">
  <br />
</p>

#

Pixels are categorised, class-averaged and mapped:
- Perform dimensionality reduction via both PCA and UMAP
    - (src.clustering.reduce)
- Categorise via K-means
    - (src.clustering.dokmeans)
- Class averages generated and stored
    - (src.clustering.complete)
- Category maps displayed for each reducer
    - (src.clustering.clustplt)

<p align="left">
  <img src="./docs/IMG/geo_clusters.png" alt="Spectrum" width="1024">
  <br />
</p>


# Usage

The tool is run as a script from core.py, or Jupyter notebook explore.ipynb

An example dataset is provided in ./data

The path to the dataset to be analysed is set in config.py, together with various flags and control parameters. 