from vnautils.librecal import LibreCAL
from vnautils.pna import PNA

import argparse
import numpy as np
import skrf
import time

CAL_SET_NAME = "LibreCAL"

def main():
    parser = argparse.ArgumentParser(
        prog = 'pna_librecal',
        description = 'Calibrate a PNA-series VNA using the LibreCAL',
    )

    parser.add_argument('filename', nargs='*')
    parser.add_argument('--port1', type=int, default=None)
    parser.add_argument('--port2', type=int, default=None)
    parser.add_argument('-f', '--force', action='store_true', help='Continue anyway if port-connection check fails')

    args = parser.parse_args()

    pna = PNA()
    lc = LibreCAL()

    # Disconnect all LibreCAL ports initially
    for i in range(1, 5):
        lc.set_port(i, "NONE")

    standards = ['SHORT', 'OPEN', 'LOAD', 'THROUGH']

    def measure():
        time.sleep(0.1)
        pna.immediate_trigger()
        pna.wait()
        n = pna.get_snp_data()
        return n

    # Turn off continuous sweep so that we can trigger & collect data on-demand
    pna.set_continuous(False)

    # Turn off correction, in case there's a previous calibration active
    pna.set_correction_state(False)

    # TODO: implement properly by creating temporary S11/S22 measurements for cal
    pna.write(":CALC:PAR:SEL CH1_S11_1")

    # Detect connected ports
    port1_candidates = []
    port2_candidates = []
    for i in range(1, 5):
        lc.set_port(i, "OPEN")
        open = measure()
        lc.set_port(i, "SHORT")
        short = measure()
        lc.set_port(i, "NONE")

        # Calculate phase difference between open/short measurements.
        # For unconnected ports this should be 0, for connected ones it should be roughly +/-pi
        s11_diff = open.s11.s*np.conjugate(short.s11.s)
        s22_diff = open.s22.s*np.conjugate(short.s22.s)

        # Average in the complex plane because the angle could be flipping between +/- pi,
        # then calculate the angle and take the absolute value
        s11_phase = np.abs(np.angle(np.average(s11_diff)))
        s22_phase = np.abs(np.angle(np.average(s22_diff)))

        if s11_phase > np.pi/2:
            port1_candidates.append(i)

        if s22_phase > np.pi/2:
            port2_candidates.append(i)

    # Check auto-detected ports against selections, or apply them if no selections
    def check_ports(port_candidates, port_selected, vna_port_name):
        # Check if selected port seems to match what we can detect
        if port_selected:
            if len(port_candidates) > 1:
                if args.force:
                    print(f"WARNING: multiple candidates found for {vna_port_name} ({port_candidates})")
                    return port_selected
                else:
                    print(f"ERROR: multiple candidates found for {vna_port_name} ({port_candidates})")
                    return -1
            elif len(port_candidates) == 0:
                if args.force:
                    print(f"WARNING: no candidates found for {vna_port_name}")
                    return port_selected
                else:
                    print(f"ERROR: no candidates found for {vna_port_name}")
                    return -1
            elif port_candidates[0] != port_selected:
                if args.force:
                    print(f"WARNING: {vna_port_name} candidate ({port_candidates[0]}) does not match selection ({port_selected})")
                    return port_selected
                else:
                    print(f"ERROR: {vna_port_name} candidate ({port_candidates[0]}) does not match selection ({port_selected})")
                    return -1
            else:
                return port_selected
        # Or if no port selected, auto-detect it
        else:
            if len(port_candidates) > 1:
                print(f"ERROR: multiple candidates found for {vna_port_name} ({port_candidates})")
                return -1
            elif len(port_candidates) == 0:
                print(f"ERROR: no candidates found for {vna_port_name}")
                return -1
            else:
                print(f"Auto-detected {vna_port_name} connection to LibreCAL port {port_candidates[0]}")
                return port_candidates[0]
    
    port1_selection = check_ports(port1_candidates, args.port1, "port1")
    if port1_selection == -1:
        return

    port2_selection = check_ports(port2_candidates, args.port2, "port2")
    if port2_selection == -1:
        return

    # Measure standards
    measured = []
    for standard in standards:
        if standard == "THROUGH":
            lc.set_port(port1_selection, standard, port2_selection)
        else:
            lc.set_port(port1_selection, standard)
            lc.set_port(port2_selection, standard)

        measured.append(measure())

    # Restart continuous sweep and turn correction back on
    pna.set_continuous(True)
    pna.set_correction_state(True)

    def ideal(standard, port1, port2):
        if standard == "THROUGH":
            if port1 > port2:
                return lc.get_snp_data(f"P{port2}{port1}_THROUGH").flipped()
            else:
                return lc.get_snp_data(f"P{port1}{port2}_THROUGH")
        else:
            s11 = lc.get_snp_data(f"P{port1}_{standard}")
            s22 = lc.get_snp_data(f"P{port2}_{standard}")
            return skrf.two_port_reflect(s11, s22)

    ideals = [ideal(standard, port1=port1_selection, port2=port2_selection) for standard in standards]

    cal = skrf.calibration.SOLT(
        ideals=ideals,
        measured=measured,
    )
    cal.run()

    eterm_map = {
        'forward directivity':              'EDIR,1,1',
        'forward source match':             'ESRM,1,1',
        'forward reflection tracking':      'ERFT,1,1',

        'forward transmission tracking':    'ETRT,2,1',
        'forward load match':               'ELDM,2,1',
        'forward isolation':                'EXTLK,2,1',


        'reverse directivity':              'EDIR,2,2',
        'reverse source match':             'ESRM,2,2',
        'reverse reflection tracking':      'ERFT,2,2',

        'reverse transmission tracking':    'ETRT,1,2',
        'reverse load match':               'ELDM,1,2',
        'reverse isolation':                'EXTLK,1,2',
    }

    # Delete cal set if it already exists
    # (the PNA software doesn't seem to let you overwrite the terms in it)
    for cs in pna.get_cal_sets():
        if cs[0] == CAL_SET_NAME:
            pna.delete_cal_set(cs[1])

    # Create a cal set, select it, and fill it with the error terms
    pna.create_cal_set(CAL_SET_NAME)
    pna.select_cal_set(CAL_SET_NAME)
    for key, item in eterm_map.items():
        values = cal.coefs_12term[key].copy().view(float)
        pna.inst.write_binary_values(f":SENS:CORR:CSET:DATA {item},", values, datatype='f')

    pna.activate_cal_set(CAL_SET_NAME)

if __name__ == "__main__":
    main()