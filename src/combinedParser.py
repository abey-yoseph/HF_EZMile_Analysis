import pandas as pd
import numpy as np
import sys
from csv import writer
from csv import reader
import difflib
import math
import geopy.distance
from scipy.signal import argrelextrema
from scipy.signal import find_peaks

#read in necessary input files
bsm_txFile = sys.argv[1] #BSM TX OBU file
bsm_rxFile = sys.argv[2] #BSM RX OBU file (shuttle)
spat_rxFile = sys.argv[3] #SPAT RX OBU file
map_rxFile = sys.argv[4] #MAP RX OBU file

testNum = bsm_txFile.split("_")[7]
trialNum = bsm_txFile.split("_")[9]
previousDistance = 0

#calculate the time left before crossing the intersection
def timeToIntersection(distance, velocity_initial):
    #using two v=x/t, t=x/v
    return distance/velocity_initial

#calculate the distance between two points using gps coordinates
def distanceBetween(txLat, txLong, rxLat, rxLong):
    txCoordinates = (float(txLat), float(txLong))
    rxCoordinates = (float(rxLat), float(rxLong))
    return geopy.distance.distance(txCoordinates, rxCoordinates).m

#calculate the time left in the phase
def phaseTime(moy, endTime):
    endTimeConverted = endTime*0.1
    minutesInCurrentHour = moy % 60
    secondsInCurrentHour = minutesInCurrentHour*60

    if endTimeConverted < secondsInCurrentHour:
        timeLeft = (60*(60-minutesInCurrentHour))+endTimeConverted

    else:
        timeLeft = endTimeConverted-secondsInCurrentHour

    return timeLeft

#function used in row by row lambda call
def lambdaHelper(row, stopLat, stopLon):
    #calculate min and max time left in the 4 signal phases
    return pd.Series([phaseTime(row['moy'], row['group2_minEndTime']),
    phaseTime(row['moy'], row['group2_maxEndTime']), phaseTime(row['moy'], row['group4_minEndTime']),
    phaseTime(row['moy'], row['group4_maxEndTime']), phaseTime(row['moy'], row['group6_minEndTime']),
    phaseTime(row['moy'], row['group6_maxEndTime']), phaseTime(row['moy'], row['group8_minEndTime']),
    phaseTime(row['moy'], row['group8_maxEndTime'])])

#returns the distance from the first location
def vehicleTravelledHelper(row, startLat, startLon):
    return distanceBetween(startLat, startLon, row['vehicle_lat'], row['vehicle_lon'])

#merges bsm tx with bsm rx based on closest time
#then merges that file with spat rx based on closest time
def combiner(bsm_txFile, bsm_rxFile, spat_rxFile, map_rxFile):
    bsmTx = pd.read_csv(f'{bsm_txFile}')
    bsmRx = pd.read_csv(f'{bsm_rxFile}')
    spatRx = pd.read_csv(f'{spat_rxFile}')
    mapRx = pd.read_csv(f'{map_rxFile}')
    bsmTx.drop('hex', axis=1, inplace=True)
    bsmRx.drop('hex', axis=1, inplace=True)
    spatRx.drop('hex', axis=1, inplace=True)

    #get the static GPS coordinates of the intersection of interest
    intersection_lat = mapRx['laneLat'].iloc[0]
    intersection_lon = mapRx['laneLong'].iloc[0]

    first_vehicle_lat = bsmTx['latitude'].iloc[0]
    first_vehicle_lon = bsmTx['longitude'].iloc[0]

    #perform left nearest merge to get closest bsm rx time from the shuttle to the bsm tx time of the test vehicle
    bsm_tx_rx_merged = pd.merge_asof(bsmTx,bsmRx,on='time',direction='nearest',allow_exact_matches=False)

    #then perform left nearest merge to get closest spat rx time from the intersection to the bsm tx time of the test vehicle
    bsm_spat_merged = pd.merge_asof(bsm_tx_rx_merged,spatRx,on='time',direction='nearest',allow_exact_matches=False)

    bsm_spat_merged.rename(columns={'time': 'vehicle_tx_time', 'latitude_x': 'vehicle_lat', 'longitude_x': 'vehicle_lon',
                      'speed(m/s)_x': 'vehicle_speed(m/s)', 'accel_long(m/s^2)_x': 'vehicle_accel_long(m/s^2)',
                      'latitude_y': 'shuttle_lat', 'longitude_y': 'shuttle_lon', 'speed(m/s)_y': 'shuttle_speed(m/s)',
                      'accel_long(m/s^2)_y': 'shuttle_accel_lon(m/s^2)'}, inplace=True)


    bsm_spat_merged[["signalgroup2_phase_minEndTime(s)","signalgroup2_phase_maxEndTime(s)", "signalgroup4_phase_minEndTime(s)",
    "signalgroup4_phase_maxEndTime(s)", "signalgroup6_phase_minEndTime(s)", "signalgroup6_phase_maxEndTime(s)",
    "signalgroup8_phase_minEndTime(s)", "signalgroup8_phase_maxEndTime(s)"]] = bsm_spat_merged.apply(lambda row: lambdaHelper(row, intersection_lat, intersection_lon), axis=1)

    bsm_spat_merged.drop(['intersectionID',	'group2_minEndTime', 'group2_maxEndTime',
    'group4_minEndTime', 'group4_maxEndTime', 'group6_minEndTime',
    'group6_maxEndTime', 'group8_minEndTime', 'group8_maxEndTime', 'moy'], axis=1, inplace=True)

    bsm_spat_merged['vehicle_distance_from_start(m)'] = bsm_spat_merged.apply(lambda row: vehicleTravelledHelper(row, first_vehicle_lat, first_vehicle_lon), axis=1)

    #figure out the number of laps that have been done during the test
    dist = bsm_spat_merged['vehicle_distance_from_start(m)']
    dist_array = np.asarray(dist)
    peaks, _ = find_peaks(dist_array*-1, distance=dist_array.max()*2+100)
    laps = len(peaks)-1

    bsm_spat_merged.loc[bsm_spat_merged.index[len(bsm_spat_merged)-1], 'num_laps'] = laps

    bsm_spat_merged.to_csv(f'Test_{testNum}_Trial_{trialNum}_combined.csv', index=False)

combiner(bsm_txFile, bsm_rxFile, spat_rxFile, map_rxFile)
