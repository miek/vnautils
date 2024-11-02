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
    parser.add_argument('--port1', type=int)
    parser.add_argument('--port2', type=int)

    args = parser.parse_args()

    pna = PNA()
    lc = LibreCAL()

    # TODO: auto-detect orientation
    # TODO: sanity check connections

    standards = ['SHORT', 'OPEN', 'LOAD', 'THROUGH']

    def measure(standard):
        if standard == "THROUGH":
            lc.set_port(args.port1, standard, args.port2)
        else:
            lc.set_port(args.port1, standard)
            lc.set_port(args.port2, standard)

        time.sleep(0.1)
        pna.immediate_trigger()
        pna.wait()
        n = pna.get_snp_data()
        n.name = standard
        return n

    pna.set_correction_state(False)
    pna.set_continuous(False)
    measured = [measure(standard) for standard in standards]
    pna.set_continuous(True)
    pna.set_correction_state(True)

    def ideal(standard, port1=1, port2=2):
        if standard == "THROUGH":
            if port1 > port2:
                return lc.get_snp_data(f"P{port2}{port1}_THROUGH").flipped()
            else:
                return lc.get_snp_data(f"P{port1}{port2}_THROUGH")
        else:
            s11 = lc.get_snp_data(f"P{port1}_{standard}")
            s22 = lc.get_snp_data(f"P{port2}_{standard}")
            return skrf.two_port_reflect(s11, s22)

    ideals = [ideal(standard, port1=args.port1, port2=args.port2) for standard in standards]

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
        term_str = ",".join(np.format_float_scientific(f) for f in values)
        pna.inst.write(f":SENS:CORR:CSET:DATA {item},{term_str}")

    pna.activate_cal_set(CAL_SET_NAME)

if __name__ == "__main__":
    main()