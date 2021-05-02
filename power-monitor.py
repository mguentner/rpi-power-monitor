#!/usr/bin/python
from time import sleep
import timeit
import csv
import copy
from math import sqrt
import sys
import influx_interface as infl
from datetime import datetime
from plotting import plot_data
import pickle
import os
from socket import socket, AF_INET, SOCK_DGRAM
import fcntl
from prettytable import PrettyTable
import logging
from config import logger, ct_phase_correction, ct0_channel, ct1_channel, ct2_channel, ct3_channel, ct4_channel, board_voltage_channel, v_sensor_channel, ct5_channel, GRID_VOLTAGE, AC_TRANSFORMER_OUTPUT_VOLTAGE, AVERAGE_SAMPLES, accuracy_calibration, db_settings
from calibration import check_phasecal, rebuild_wave, find_phasecal
from textwrap import dedent
from common import collect_data, readadc, recover_influx_container
from shutil import copyfile



# Tuning Variables


# Static Variables - these should not be changed by the end user
AC_voltage_ratio            = (GRID_VOLTAGE / AC_TRANSFORMER_OUTPUT_VOLTAGE) * 11   # This is a rough approximation of the ratio
# Phase Calibration - note that these items are listed in the order they are sampled.
# Changes to these values are made in config.py, in the ct_phase_correction dictionary.
ct0_phasecal = ct_phase_correction['ct0']
ct4_phasecal = ct_phase_correction['ct4']
ct1_phasecal = ct_phase_correction['ct1']
ct2_phasecal = ct_phase_correction['ct2']
ct3_phasecal = ct_phase_correction['ct3']
ct5_phasecal = ct_phase_correction['ct5']
ct0_accuracy_factor         = accuracy_calibration['ct0']
ct1_accuracy_factor         = accuracy_calibration['ct1']
ct2_accuracy_factor         = accuracy_calibration['ct2']
ct3_accuracy_factor         = accuracy_calibration['ct3']
ct4_accuracy_factor         = accuracy_calibration['ct4']
ct5_accuracy_factor         = accuracy_calibration['ct5']
AC_voltage_accuracy_factor  = accuracy_calibration['AC']



def dump_data(dump_type, samples):
    speed_kHz = spi.max_speed_hz / 1000
    now = datetime.now().stfrtime('%m-%d-%Y-%H-%M')
    filename = f'data-dump-{now}.csv'
    with open(filename, 'w') as f:
        headers = ["Sample#", "ct0", "ct1", "ct2", "ct3", "ct4", "ct5", "voltage"]
        writer = csv.writer(f)
        writer.writerow(headers)
        # samples contains lists for each data sample. 
        for i in range(0, len(samples[0])):
            ct0_data = samples[0]
            ct1_data = samples[1]
            ct2_data = samples[2]
            ct3_data = samples[3]
            ct4_data = samples[4]
            ct5_data = samples[5]
            v_data = samples[-1]
            writer.writerow([i, ct0_data[i], ct1_data[i], ct2_data[i], ct3_data[i], ct4_data[i], ct5_data[i], v_data[i]])
    logger.info(f"CSV written to {filename}.")

def get_board_voltage():
    # Take 10 sample readings and return the average board voltage from the +3.3V rail. 
    samples = []
    while len(samples) <= 10:
        data = readadc(board_voltage_channel)
        samples.append(data)

    avg_reading = sum(samples) / len(samples)
    board_voltage = (avg_reading / 1024) * 3.31 * 2
    return board_voltage

# Phase corrected power calculation
def calculate_power(samples, board_voltage):
    ct0_samples = samples['ct0']        # current samples for CT0
    ct1_samples = samples['ct1']        # current samples for CT1
    ct2_samples = samples['ct2']        # current samples for CT2
    ct3_samples = samples['ct3']        # current samples for CT3
    ct4_samples = samples['ct4']        # current samples for CT4
    ct5_samples = samples['ct5']        # current samples for CT5
    v_samples_0 = samples['v_ct0']      # phase-corrected voltage wave specifically for CT0
    v_samples_1 = samples['v_ct1']      # phase-corrected voltage wave specifically for CT1
    v_samples_2 = samples['v_ct2']      # phase-corrected voltage wave specifically for CT2
    v_samples_3 = samples['v_ct3']      # phase-corrected voltage wave specifically for CT3
    v_samples_4 = samples['v_ct4']      # phase-corrected voltage wave specifically for CT4   
    v_samples_5 = samples['v_ct5']      # phase-corrected voltage wave specifically for CT5   

    # Variable Initialization    
    sum_inst_power_ct0 = 0
    sum_inst_power_ct1 = 0
    sum_inst_power_ct2 = 0
    sum_inst_power_ct3 = 0
    sum_inst_power_ct4 = 0
    sum_inst_power_ct5 = 0
    sum_squared_current_ct0 = 0 
    sum_squared_current_ct1 = 0
    sum_squared_current_ct2 = 0
    sum_squared_current_ct3 = 0
    sum_squared_current_ct4 = 0
    sum_squared_current_ct5 = 0
    sum_raw_current_ct0 = 0
    sum_raw_current_ct1 = 0
    sum_raw_current_ct2 = 0
    sum_raw_current_ct3 = 0
    sum_raw_current_ct4 = 0
    sum_raw_current_ct5 = 0
    sum_squared_voltage_0 = 0
    sum_squared_voltage_1 = 0
    sum_squared_voltage_2 = 0
    sum_squared_voltage_3 = 0
    sum_squared_voltage_4 = 0
    sum_squared_voltage_5 = 0
    sum_raw_voltage_0 = 0
    sum_raw_voltage_1 = 0
    sum_raw_voltage_2 = 0
    sum_raw_voltage_3 = 0
    sum_raw_voltage_4 = 0
    sum_raw_voltage_5 = 0

    # Scaling factors
    vref = board_voltage / 1024
    ct0_scaling_factor = vref * 100 * ct0_accuracy_factor
    ct1_scaling_factor = vref * 100 * ct1_accuracy_factor
    ct2_scaling_factor = vref * 100 * ct2_accuracy_factor
    ct3_scaling_factor = vref * 100 * ct3_accuracy_factor
    ct4_scaling_factor = vref * 100 * ct4_accuracy_factor
    ct5_scaling_factor = vref * 100 * ct5_accuracy_factor
    voltage_scaling_factor = vref * AC_voltage_ratio * AC_voltage_accuracy_factor


    num_samples = len(v_samples_0)

    for i in range(0, num_samples):
        ct0 = (int(ct0_samples[i]))
        ct1 = (int(ct1_samples[i]))
        ct2 = (int(ct2_samples[i]))
        ct3 = (int(ct3_samples[i]))
        ct4 = (int(ct4_samples[i]))
        ct5 = (int(ct5_samples[i]))
        voltage_0 = (int(v_samples_0[i]))
        voltage_1 = (int(v_samples_1[i]))
        voltage_2 = (int(v_samples_2[i]))
        voltage_3 = (int(v_samples_3[i]))
        voltage_4 = (int(v_samples_4[i]))
        voltage_5 = (int(v_samples_5[i]))

        # Process all data in a single function to reduce runtime complexity
        # Get the sum of all current samples individually
        sum_raw_current_ct0 += ct0
        sum_raw_current_ct1 += ct1
        sum_raw_current_ct2 += ct2
        sum_raw_current_ct3 += ct3
        sum_raw_current_ct4 += ct4
        sum_raw_current_ct5 += ct5
        sum_raw_voltage_0 += voltage_0
        sum_raw_voltage_1 += voltage_1
        sum_raw_voltage_2 += voltage_2
        sum_raw_voltage_3 += voltage_3
        sum_raw_voltage_4 += voltage_4
        sum_raw_voltage_5 += voltage_5


        # Calculate instant power for each ct sensor
        inst_power_ct0 = ct0 * voltage_0
        inst_power_ct1 = ct1 * voltage_1
        inst_power_ct2 = ct2 * voltage_2
        inst_power_ct3 = ct3 * voltage_3
        inst_power_ct4 = ct4 * voltage_4
        inst_power_ct5 = ct5 * voltage_5
        sum_inst_power_ct0 += inst_power_ct0
        sum_inst_power_ct1 += inst_power_ct1
        sum_inst_power_ct2 += inst_power_ct2
        sum_inst_power_ct3 += inst_power_ct3
        sum_inst_power_ct4 += inst_power_ct4
        sum_inst_power_ct5 += inst_power_ct5

        # Squared voltage
        squared_voltage_0 = voltage_0 * voltage_0
        squared_voltage_1 = voltage_1 * voltage_1
        squared_voltage_2 = voltage_2 * voltage_2
        squared_voltage_3 = voltage_3 * voltage_3
        squared_voltage_4 = voltage_4 * voltage_4
        squared_voltage_5 = voltage_5 * voltage_5
        sum_squared_voltage_0 += squared_voltage_0
        sum_squared_voltage_1 += squared_voltage_1
        sum_squared_voltage_2 += squared_voltage_2
        sum_squared_voltage_3 += squared_voltage_3
        sum_squared_voltage_4 += squared_voltage_4
        sum_squared_voltage_5 += squared_voltage_5

        # Squared current
        sq_ct0 = ct0 * ct0
        sq_ct1 = ct1 * ct1
        sq_ct2 = ct2 * ct2
        sq_ct3 = ct3 * ct3
        sq_ct4 = ct4 * ct4
        sq_ct5 = ct5 * ct5

        sum_squared_current_ct0 += sq_ct0
        sum_squared_current_ct1 += sq_ct1
        sum_squared_current_ct2 += sq_ct2
        sum_squared_current_ct3 += sq_ct3
        sum_squared_current_ct4 += sq_ct4
        sum_squared_current_ct5 += sq_ct5

    avg_raw_current_ct0 = sum_raw_current_ct0 / num_samples
    avg_raw_current_ct1 = sum_raw_current_ct1 / num_samples
    avg_raw_current_ct2 = sum_raw_current_ct2 / num_samples
    avg_raw_current_ct3 = sum_raw_current_ct3 / num_samples
    avg_raw_current_ct4 = sum_raw_current_ct4 / num_samples
    avg_raw_current_ct5 = sum_raw_current_ct5 / num_samples
    avg_raw_voltage_0 = sum_raw_voltage_0 / num_samples
    avg_raw_voltage_1 = sum_raw_voltage_1 / num_samples
    avg_raw_voltage_2 = sum_raw_voltage_2 / num_samples
    avg_raw_voltage_3 = sum_raw_voltage_3 / num_samples
    avg_raw_voltage_4 = sum_raw_voltage_4 / num_samples
    avg_raw_voltage_5 = sum_raw_voltage_5 / num_samples

    real_power_0 = ((sum_inst_power_ct0 / num_samples) - (avg_raw_current_ct0 * avg_raw_voltage_0))  * ct0_scaling_factor * voltage_scaling_factor
    real_power_1 = ((sum_inst_power_ct1 / num_samples) - (avg_raw_current_ct1 * avg_raw_voltage_1))  * ct1_scaling_factor * voltage_scaling_factor 
    real_power_2 = ((sum_inst_power_ct2 / num_samples) - (avg_raw_current_ct2 * avg_raw_voltage_2))  * ct2_scaling_factor * voltage_scaling_factor 
    real_power_3 = ((sum_inst_power_ct3 / num_samples) - (avg_raw_current_ct3 * avg_raw_voltage_3))  * ct3_scaling_factor * voltage_scaling_factor 
    real_power_4 = ((sum_inst_power_ct4 / num_samples) - (avg_raw_current_ct4 * avg_raw_voltage_4))  * ct4_scaling_factor * voltage_scaling_factor 
    real_power_5 = ((sum_inst_power_ct5 / num_samples) - (avg_raw_current_ct5 * avg_raw_voltage_5))  * ct5_scaling_factor * voltage_scaling_factor 

    mean_square_current_ct0 = sum_squared_current_ct0 / num_samples
    mean_square_current_ct1 = sum_squared_current_ct1 / num_samples
    mean_square_current_ct2 = sum_squared_current_ct2 / num_samples
    mean_square_current_ct3 = sum_squared_current_ct3 / num_samples
    mean_square_current_ct4 = sum_squared_current_ct4 / num_samples
    mean_square_current_ct5 = sum_squared_current_ct5 / num_samples
    mean_square_voltage_0 = sum_squared_voltage_0 / num_samples
    mean_square_voltage_1 = sum_squared_voltage_1 / num_samples
    mean_square_voltage_2 = sum_squared_voltage_2 / num_samples
    mean_square_voltage_3 = sum_squared_voltage_3 / num_samples
    mean_square_voltage_4 = sum_squared_voltage_4 / num_samples
    mean_square_voltage_5 = sum_squared_voltage_5 / num_samples

    rms_current_ct0 = sqrt(mean_square_current_ct0 - (avg_raw_current_ct0 * avg_raw_current_ct0)) * ct0_scaling_factor
    rms_current_ct1 = sqrt(mean_square_current_ct1 - (avg_raw_current_ct1 * avg_raw_current_ct1)) * ct1_scaling_factor
    rms_current_ct2 = sqrt(mean_square_current_ct2 - (avg_raw_current_ct2 * avg_raw_current_ct2)) * ct2_scaling_factor
    rms_current_ct3 = sqrt(mean_square_current_ct3 - (avg_raw_current_ct3 * avg_raw_current_ct3)) * ct3_scaling_factor
    rms_current_ct4 = sqrt(mean_square_current_ct4 - (avg_raw_current_ct4 * avg_raw_current_ct4)) * ct4_scaling_factor
    rms_current_ct5 = sqrt(mean_square_current_ct5 - (avg_raw_current_ct5 * avg_raw_current_ct5)) * ct5_scaling_factor
    rms_voltage_0     = sqrt(mean_square_voltage_0 - (avg_raw_voltage_0 * avg_raw_voltage_0)) * voltage_scaling_factor
    rms_voltage_1     = sqrt(mean_square_voltage_1 - (avg_raw_voltage_1 * avg_raw_voltage_1)) * voltage_scaling_factor
    rms_voltage_2     = sqrt(mean_square_voltage_2 - (avg_raw_voltage_2 * avg_raw_voltage_2)) * voltage_scaling_factor
    rms_voltage_3     = sqrt(mean_square_voltage_3 - (avg_raw_voltage_3 * avg_raw_voltage_3)) * voltage_scaling_factor
    rms_voltage_4     = sqrt(mean_square_voltage_4 - (avg_raw_voltage_4 * avg_raw_voltage_4)) * voltage_scaling_factor
    rms_voltage_5     = sqrt(mean_square_voltage_5 - (avg_raw_voltage_5 * avg_raw_voltage_5)) * voltage_scaling_factor

    # Power Factor
    apparent_power_0 = rms_voltage_0 * rms_current_ct0
    apparent_power_1 = rms_voltage_1 * rms_current_ct1
    apparent_power_2 = rms_voltage_2 * rms_current_ct2
    apparent_power_3 = rms_voltage_3 * rms_current_ct3
    apparent_power_4 = rms_voltage_4 * rms_current_ct4
    apparent_power_5 = rms_voltage_5 * rms_current_ct5

    try:
        power_factor_0 = real_power_0 / apparent_power_0
    except ZeroDivisionError:
        power_factor_0 = 0
    try:
        power_factor_1 = real_power_1 / apparent_power_1
    except ZeroDivisionError:
        power_factor_1 = 0
    try:
        power_factor_2 = real_power_2 / apparent_power_2
    except ZeroDivisionError:
        power_factor_2 = 0
    try:
        power_factor_3 = real_power_3 / apparent_power_3
    except ZeroDivisionError:
        power_factor_3 = 0
    try:
        power_factor_4 = real_power_4 / apparent_power_4
    except ZeroDivisionError:
        power_factor_4 = 0
    try:
        power_factor_5 = real_power_5 / apparent_power_5
    except ZeroDivisionError:
        power_factor_5 = 0

    results = {
        'ct0' : {
            'power'     : real_power_0,
            'current'   : rms_current_ct0,
            'voltage'   : rms_voltage_0,
            'pf'        : power_factor_0
        },
        'ct1' : {
            'power'     : real_power_1,
            'current'   : rms_current_ct1,
            'voltage'   : rms_voltage_1,
            'pf'        : power_factor_1
        },
        'ct2' : {
            'power'     : real_power_2,
            'current'   : rms_current_ct2,
            'voltage'   : rms_voltage_2,
            'pf'        : power_factor_2
        },
        'ct3' : {
            'power'     : real_power_3,
            'current'   : rms_current_ct3,
            'voltage'   : rms_voltage_3,
            'pf'        : power_factor_3
        },
        'ct4' : {
            'power'     : real_power_4,
            'current'   : rms_current_ct4,
            'voltage'   : rms_voltage_4,
            'pf'        : power_factor_4
        },
        'ct5' : {
            'power'     : real_power_5,
            'current'   : rms_current_ct5,
            'voltage'   : rms_voltage_5,
            'pf'        : power_factor_5
        },
        'voltage' : rms_voltage_0,
    }

    return results

def average_samples(samples):
    def add_values(a,b):
        if isinstance(a, (float, int)):
            return a + b
        elif isinstance(a, dict):
            return { k: add_values(v, b[k]) for k, v in a.items() }

    def average(values, num):
        if isinstance(values, (float, int)):
            return values/num
        elif isinstance(values, dict):
            return { k: average(v, num) for k, v in values.items() }
        raise "Invalid Type"

    averaged = None
    for sample in samples:
        if averaged is None:
            averaged = copy.deepcopy(sample)
        else:
            averaged = {key: add_values(value, sample[key]) for key, value in averaged.items() }
    return average(averaged, len(samples))


def rebuild_waves(samples, PHASECAL_0, PHASECAL_1, PHASECAL_2, PHASECAL_3, PHASECAL_4, PHASECAL_5):

    # The following empty lists will hold the phase corrected voltage wave that corresponds to each individual CT sensor.
    wave_0 = []
    wave_1 = []
    wave_2 = []
    wave_3 = []
    wave_4 = []
    wave_5 = []

    voltage_samples = samples['voltage']

    wave_0.append(voltage_samples[0])
    wave_1.append(voltage_samples[0])
    wave_2.append(voltage_samples[0])
    wave_3.append(voltage_samples[0])
    wave_4.append(voltage_samples[0])
    wave_5.append(voltage_samples[0])
    previous_point = voltage_samples[0]

    for current_point in voltage_samples[1:]:
        new_point_0 = previous_point + PHASECAL_0 * (current_point - previous_point)
        new_point_1 = previous_point + PHASECAL_1 * (current_point - previous_point)
        new_point_2 = previous_point + PHASECAL_2 * (current_point - previous_point)
        new_point_3 = previous_point + PHASECAL_3 * (current_point - previous_point)
        new_point_4 = previous_point + PHASECAL_4 * (current_point - previous_point)
        new_point_5 = previous_point + PHASECAL_5 * (current_point - previous_point)

        wave_0.append(new_point_0)
        wave_1.append(new_point_1)
        wave_2.append(new_point_2)
        wave_3.append(new_point_3)
        wave_4.append(new_point_4)
        wave_5.append(new_point_5)

        previous_point = current_point

    rebuilt_waves = {
        'v_ct0' : wave_0,
        'v_ct1' : wave_1,
        'v_ct2' : wave_2,
        'v_ct3' : wave_3,
        'v_ct4' : wave_4,
        'v_ct5' : wave_5,
        'voltage' : voltage_samples,
        'ct0' : samples['ct0'],
        'ct1' : samples['ct1'],
        'ct2' : samples['ct2'],
        'ct3' : samples['ct3'],
        'ct4' : samples['ct4'],
        'ct5' : samples['ct5'],
    }

    return rebuilt_waves


def run_main():
    logger.info("... Starting Raspberry Pi Power Monitor")
    logger.info("Press Ctrl-c to quit...")
    rms_voltages = []
    i = 0   # Counter for aggregate function
    sample_memory = []

    while True:
        try:
            board_voltage = get_board_voltage()
            samples = collect_data(2000)
            poll_time = samples['time']
            ct0_samples = samples['ct0']
            ct1_samples = samples['ct1']
            ct2_samples = samples['ct2']
            ct3_samples = samples['ct3']
            ct4_samples = samples['ct4']
            ct5_samples = samples['ct5']
            v_samples = samples['voltage']
            rebuilt_waves = rebuild_waves(samples, ct0_phasecal, ct1_phasecal, ct2_phasecal, ct3_phasecal, ct4_phasecal, ct5_phasecal)
            results = calculate_power(rebuilt_waves, board_voltage)
            sample_memory.append(results)
            if len(sample_memory) > AVERAGE_SAMPLES:
                averaged = average_samples(sample_memory[-AVERAGE_SAMPLES:])
                infl.write_to_influx(averaged)
                if logger.handlers[0].level == 10:
                    print_results(averaged)
                sample_memory = sample_memory[-AVERAGE_SAMPLES:]
        except KeyboardInterrupt:
            sys.exit()

def print_results(results):
    t = PrettyTable(['', 'CT0', 'CT1', 'CT2', 'CT3', 'CT4', 'CT5'])
    t.add_row(['Watts', round(results['ct0']['power'], 3), round(results['ct1']['power'], 3), round(results['ct2']['power'], 3), round(results['ct3']['power'], 3), round(results['ct4']['power'], 3), round(results['ct5']['power'], 3)])
    t.add_row(['Current', round(results['ct0']['current'], 3), round(results['ct1']['current'], 3), round(results['ct2']['current'], 3), round(results['ct3']['current'], 3), round(results['ct4']['current'], 3), round(results['ct5']['current'], 3)])
    t.add_row(['P.F.', round(results['ct0']['pf'], 3), round(results['ct1']['pf'], 3), round(results['ct2']['pf'], 3), round(results['ct3']['pf'], 3), round(results['ct4']['pf'], 3), round(results['ct5']['pf'], 3)])
    t.add_row(['Voltage', round(results['voltage'], 3), '', '', '', '', ''])
    s = t.get_string()
    logger.debug(s)

def run_phase_calibration():
    # This mode is intended to be used for correcting the phase error in your CT sensors. Please ensure that you have a purely resistive load running through your CT sensors - that means no electric fans and no digital circuitry!

    PF_ROUNDING_DIGITS = 3      # This variable controls how many decimal places the PF will be rounded

    while True:
        try:
            ct_num = int(input("\nWhich CT number are you calibrating? Enter the number of the CT label [0 - 5]: "))
            if ct_num not in range(0, 6):
                logger.error("Please choose from CT numbers 0, 1, 2, 3, 4, or 5.")
            else:
                ct_selection = f'ct{ct_num}'
                break
        except ValueError:
            logger.error("Please enter an integer! Acceptable choices are: 0, 1, 2, 3, 4, 5.")


    cont = input(dedent(f"""
        #------------------------------------------------------------------------------#
        # IMPORTANT: Make sure that current transformer {ct_selection} is installed over          #
        #            a purely resistive load and that the load is turned on            #
        #            before continuing with the calibration!                           #
        #------------------------------------------------------------------------------#

        Continue? [y/yes/n/no]: """))

    if cont.lower() in ['n', 'no']:
        logger.info("\nCalibration Aborted.\n")
        sys.exit()

    samples = collect_data(2000)
    rebuilt_wave = rebuild_wave(samples[ct_selection], samples['voltage'], ct_phase_correction[ct_selection])
    board_voltage = get_board_voltage()
    results = check_phasecal(rebuilt_wave['ct'], rebuilt_wave['new_v'], board_voltage)

    # Get the current power factor and check to make sure it is not negative. If it is, the CT is installed opposite to how it should be.
    pf = results['pf']
    initial_pf = pf
    if pf < 0:
        logger.info(dedent('''
            Current transformer is installed backwards. Please reverse the direction that it is attached to your load. \n
            (Unclip it from your conductor, and clip it on so that the current flows the opposite direction from the CT's perspective) \n
            Press ENTER to continue when you've reversed your CT.'''))
        input("[ENTER]")
        # Check to make sure the CT was reversed properly by taking another batch of samples/calculations:
        samples = collect_data(2000)
        rebuilt_wave = rebuild_wave(samples[ct_selection], samples['voltage'], 1)
        board_voltage = get_board_voltage()
        results = check_phasecal(rebuilt_wave['ct'], rebuilt_wave['new_v'], board_voltage)
        pf = results['pf']
        if pf < 0:
            logger.info(dedent("""It still looks like the current transformer is installed backwards.  Are you sure this is a resistive load?\n
                Please consult the project documentation on https://github.com/david00/rpi-power-monitor/wiki and try again."""))
            sys.exit()

    # Initialize phasecal values
    new_phasecal = ct_phase_correction[ct_selection]
    previous_pf = 0
    new_pf = pf

    samples = collect_data(2000)
    board_voltage = get_board_voltage()
    best_pfs = find_phasecal(samples, ct_selection, PF_ROUNDING_DIGITS, board_voltage)
    avg_phasecal = sum([x['cal'] for x in best_pfs]) / len([x['cal'] for x in best_pfs])
    logger.info(f"Please update the value for {ct_selection} in ct_phase_correction in config.py with the following value: {round(avg_phasecal, 8)}")
    logger.info("Please wait... building HTML plot...")
    # Get new set of samples using recommended phasecal value
    samples = collect_data(2000)
    rebuilt_wave = rebuild_wave(samples[ct_selection], samples['voltage'], avg_phasecal)

    report_title = f'CT{ct_num}-phase-correction-result'
    plot_data(rebuilt_wave, report_title, ct_selection)
    logger.info(f"file written to {report_title}.html")


def run_debug():
    # This mode is intended to take a look at the raw CT sensor data.  It will take 2000 samples from each CT sensor, plot them to a single chart, write the chart to an HTML file located in /var/www/html/, and then terminate.
    # It also stores the samples to a file located in ./data/samples/last-debug.pkl so that the sample data can be read when this program is started in 'phase' mode.
    # Time sample collection
    start = timeit.default_timer()
    samples = collect_data(2000)
    stop = timeit.default_timer()
    duration = stop - start

    # Calculate Sample Rate in Kilo-Samples Per Second.
    sample_count = sum([ len(samples[x]) for x in samples.keys() if type(samples[x]) == list ])

    print(f"sample count is {sample_count}")
    sample_rate = round((sample_count / duration) / 1000, 2)

    logger.debug(f"Finished Collecting Samples. Sample Rate: {sample_rate} KSPS")
    ct0_samples = samples['ct0']
    ct1_samples = samples['ct1']
    ct2_samples = samples['ct2']
    ct3_samples = samples['ct3']
    ct4_samples = samples['ct4']
    ct5_samples = samples['ct5']
    v_samples = samples['voltage']

    # Save samples to disk
    with open('data/samples/last-debug.pkl', 'wb') as f:
        pickle.dump(samples, f)

    if not title:
        title = input("Enter the title for this chart: ")

    title = title.replace(" ","_")
    logger.debug("Building plot.")
    plot_data(samples, title, sample_rate=sample_rate)
    ip = get_ip()
    if ip:
        logger.info(f"Chart created! Visit http://{ip}/{title}.html to view the chart. Or, simply visit http://{ip} to view all the charts created using 'debug' and/or 'phase' mode.")
    else:
        logger.info("Chart created! I could not determine the IP address of this machine. Visit your device's IP address in a webrowser to view the list of charts you've created using 'debug' and/or 'phase' mode.")


def get_ip():
    # This function acquires your Pi's local IP address for use in providing the user with a copy-able link to view the charts.
    # It does so by trying to connect to a non-existent private IP address, but in doing so, it is able to detect the IP address associated with the default route.
    s = socket(AF_INET, SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except:
        IP = None
    finally:
        s.close()
    return IP


if __name__ == '__main__':

    # Backup config.py file
    try:
        copyfile('config.py', 'config.py.backup')
    except FileNotFoundError:
        logger.info("Could not create a backup of config.py file.")

    if len(sys.argv) > 1:
        MODE = sys.argv[1]
        if MODE == 'debug' or MODE == 'phase':
            try:
                title = sys.argv[2]
            except IndexError:
                title = None
        # Create the data/samples directory:
        try:
            os.makedirs('data/samples/')
        except FileExistsError:
            pass
    else:
        MODE = "default"

    if MODE not in ["default", "phase", "debug"]:
        if not infl.init_db():
            logger.info("Could not connect to your remote database. Please verify this Pi can connect to your database and then try running the software again.")
            sys.exit()

    if MODE.lower() != "default":
        logger.setLevel(logging.DEBUG)
        logger.handlers[0].setLevel(logging.DEBUG)

    # Program launched in one of the non-main modes. Increase logging level.
    if 'help' in MODE.lower() or '-h' in MODE.lower():

        logger.info("See the project Wiki for more detailed usage instructions: https://github.com/David00/rpi-power-monitor/wiki")
        logger.info(dedent("""Usage:
            Start the program:                                  python3 power-monitor.py

            Collect raw data and build an interactive plot:     python3 power-monitor.py debug "chart title here"

            Launch interactive phase correction mode:           python3 power-monitor.py phase

            Start the program like normal, but print all        python3 power-monitor.py terminal
            readings to the terminal window
            """))
    elif MODE.lower() == 'debug':
        run_debug()
    elif MODE.lower() == "phase":
        run_phase_calibration()
    elif MODE.lower() == "terminal" or MODE.lower() == "default":
        logger.debug("... Starting program in terminal mode")
        run_main()
