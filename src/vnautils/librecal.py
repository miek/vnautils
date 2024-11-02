from enum import StrEnum
import io
import numpy as np
import pyvisa
import skrf

class LibreCAL:
    def __init__(self):
        # TODO: find appropriate port by looking up VID/PID
        port = "/dev/ttyACM0"

        rm = pyvisa.ResourceManager('@py')
        self.inst = rm.open_resource(f"ASRL{port}::INSTR")
        self.inst.read_termination = "\r\n"

        #try:
        #    while True:
        #       self.inst.read()
        #except:
        #    pass

        manufacturer, model, serial, version = self.read('*IDN?').split(",")
        if manufacturer != "LibreCAL" or model != "LibreCAL":
            raise RuntimeError(f"Unsupported device found: {manufacturer} {model}")


    def write(self, command):
        self.inst.write(command)

    def read(self, command):
        return self.inst.query(command)


    def get_snp_data(self, coefficient_name, set_name="FACTORY"):
        snp_file = ""
        if self.read(f"COEFF:GET? {set_name} {coefficient_name}") == "START":
            while True:
                line = self.inst.read()
                if line == "END":
                    break
                snp_file += line + "\n"
    
        extension = ".s2p" if "THROUGH" in coefficient_name else ".s1p"
        snp_stringio = io.StringIO(snp_file)
        snp_stringio.name = coefficient_name + extension
        network = skrf.Network(file=snp_stringio)
        return network

    def set_port(self, port, standard, dest=None):
        if standard == "THROUGH":
            self.read(f":PORT {port} THROUGH {dest}")
        else:
            self.read(f":PORT {port} {standard}")
