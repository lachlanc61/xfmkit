
import csv
import re
import numpy as np

testpath="/home/lachlan/CODEBASE/ReadoutXFM/data/diagnostics_map1_evts.log"
testname="map1"

NDET=2

def dtfromdiag(filepath: str, fname: str):
    """
    extracts per-pixel deadtime values from IXRF diagnostic file

    (IXRF uses nonstandard utf8-as-utf16 format with null bytes)
    
    IMPORTANT: requires diagnostic files to be converted via sed:
    """
        #   sed -i 's/\x0//g' diagnostics_map1_evts.log

    with open(filepath) as f:
        nlines_init=sum(1 for line in f)
        print(nlines_init)
        f.seek(0)

        rt=np.zeros((NDET, nlines_init), dtype=float)
        lt=np.zeros((NDET, nlines_init), dtype=float)
        tr=np.zeros((NDET, nlines_init), dtype=int)
        ev=np.zeros((NDET, nlines_init), dtype=int)
        ocr=np.zeros((NDET, nlines_init), dtype=float)
        icr=np.zeros((NDET, nlines_init), dtype=float)
        dt=np.zeros((NDET, nlines_init), dtype=float)

        print(rt.shape, rt[1], nlines_init)

        nlines=0
        npx=0
        nmaps=0
        cdet=0

        for line in csv.reader(f):
            if "Map Acquire start" in line[0]:
                print(f"Map started at line: {nlines}")
                nmaps += 1
            if "Deadtime realtime" in line[0]:
                print(line)
                rt[cdet, npx] = float(re.findall("[\d]+[\.]\d+", line[0])[0])      
                lt[cdet, npx] = float(re.findall("[-+]?[.]?[\d]+(?:,\d\d\d)*[\.]?\d*(?:[eE][-+]?\d+)?", line[1])[0])
                tr[cdet, npx ]= int(re.findall("[-+]?[.]?[\d]+(?:,\d\d\d)*[\.]?\d*(?:[eE][-+]?\d+)?", line[2])[0])
                ev[cdet, npx] = int(re.findall("[-+]?[.]?[\d]+(?:,\d\d\d)*[\.]?\d*(?:[eE][-+]?\d+)?", line[3])[0])
                ocr[cdet, npx ]= float(re.findall("[-+]?[.]?[\d]+(?:,\d\d\d)*[\.]?\d*(?:[eE][-+]?\d+)?", line[4])[0])
                icr[cdet, npx] = float(re.findall("[-+]?[.]?[\d]+(?:,\d\d\d)*[\.]?\d*(?:[eE][-+]?\d+)?", line[5])[0])
                print(cdet, rt[cdet, npx], lt[cdet, npx], tr[cdet, npx], ev[cdet, npx], ocr[cdet, npx], icr[cdet, npx] )
            
            if "deadtime[0]" in line[0]:
                #print("DEADTIME0")
                if not cdet == 0: 
                    raise ValueError(f"Detector: expected 0, found {cdet} at line {nlines}, pixel {npx} ")
                dt[cdet, npx] = float(re.findall("[\d]+[\.]\d+", line[0])[0])
                cdet=1  #next detector

            if "deadtime[1]" in line[0]:
                #print("DEADTIME1")
                if not cdet == 1: 
                    raise ValueError(f"Detector: expected 0, found {cdet} at line {nlines}, pixel {npx} ")
                dt[cdet, npx] = float(re.findall("[\d]+[\.]\d+", line[0])[0])
                cdet=0  #first detector
                npx+=1  #next pixel

            if "Saving geoPIXE map file as" in line[0]:    #35 = character count for end of prestring
                if fname in line[0]:
                    nlines+=1
                    break
                elif nmaps > 1:
                    print("WRONG MAP: resetting")
                    rt=np.zeros((NDET, nlines_init), dtype=float)
                    lt=np.zeros((NDET, nlines_init), dtype=float)
                    tr=np.zeros((NDET, nlines_init), dtype=int)
                    ev=np.zeros((NDET, nlines_init), dtype=int)
                    ocr=np.zeros((NDET, nlines_init), dtype=float)
                    icr=np.zeros((NDET, nlines_init), dtype=float)
                    dt=np.zeros((NDET, nlines_init), dtype=float)
                    npx=0
            nlines+=1    

        rt=rt[:, :npx]
        lt=lt[:, :npx]
        tr=tr[:, :npx]
        ev=ev[:, :npx]
        ocr=ocr[:, :npx]
        icr=icr[:, :npx]
        dt=dt[:, :npx]
        calc_dt_io=np.zeros((NDET, len(dt)), dtype=float)
        #calc_dt_evts=np.zeros((NDET, len(dt)), dtype=float)
        #calc_dt_realtime=np.zeros((NDET, len(dt)), dtype=float)
        calc_dt_io=100*(1-ocr/icr)
        calc_dt_rt=100*(rt-lt)/rt

    print(f"last values: {rt[1, -1]} {lt[1, -1]} {tr[1, -1]} {ev[1, -1]} {icr[1, -1]} {ocr[1, -1]} {dt[1, -1]}")

    print(f"lines found: {nlines_init}, lines read: {nlines}, pixels: {npx}, stored: {len(rt[0])}")

#    print("ICR")
#    print(icr)
#    print("OCR")
#    print(ocr)
#    print("calc ICR")
#    print(calc_dt_io)
#    print("calc RT")
#    print(calc_dt_rt)
#    print("dt")
#    print(dt)
    print(f"IXRF  -- max: {round(np.max(dt),2)}, avg: {round(np.average(dt),2)}")
    print(f"rt/lt -- max: {round(np.max(calc_dt_rt),2)}, avg: {round(np.average(calc_dt_rt),2)}")
#    print(np.max(dt))
#    print(np.max(calc_dt_rt))

    return rt, lt, tr, ev, icr, ocr, calc_dt_rt


if __name__ == "__main__":
    dtfromdiag(testpath, testname)