from enum import StrEnum
import numpy as np
import pyvisa
import skrf

class PNA:

    _supported_models = [
        "E8801A",
        "E8802A",
        "E8803A",
        "E8356A",
        "E8357A",
        "E8358A",
    ]

    class ByteOrder(StrEnum):
        BIG = "NORM"
        LITTLE = "SWAP"

    class DataFormat(StrEnum):
        ASCII = "ASC,0"
        REAL32 = "REAL,32"
        REAL64 = "REAL,64"
    
    class StoreFormat(StrEnum):
        LINEAR_MAG = "MA"
        LOG_MAG = "DB"
        COMPLEX = "RI"
        AUTO = "AUTO"
    
    data_format = None

    def __init__(self, hostname="pna.lan", port=5025, use_binary_transfers=False):
        rm = pyvisa.ResourceManager('@py')
        self.inst = rm.open_resource(f"TCPIP0::{hostname}::{port}::SOCKET")
        self.inst.read_termination = "\n"
        timeout = 2 * 1000 + 10

        old_timeout = self.inst.timeout
        self.inst.timeout = timeout * 1000

        manufacturer, model, *_ = self.read('*IDN?').split(",")
        if not model in self._supported_models:
            raise RuntimeError(f"Unsupported model: {model}")
        
        self.set_byte_order(self.ByteOrder.LITTLE)
        if use_binary_transfers:
            self.set_data_format(self.DataFormat.REAL32)
        else:
            self.set_data_format(self.DataFormat.ASCII)
        self.set_snp_store_format(self.StoreFormat.COMPLEX)


    def write(self, command):
        self.inst.write(command)

    def read(self, command):
        return self.inst.query(command)
    
    def wait(self):
        return self.read("*OPC?")

    # Calc
    def get_snp_data(self, channel=1, port_count=2):
        cmd = f"CALC{channel}:DATA:SNP? {port_count}"
        match self.data_format:
            case self.DataFormat.ASCII:
                values = self.inst.query_ascii_values(cmd)
            case self.DataFormat.REAL32:
                values = self.inst.query_binary_values(cmd, datatype='f')
            case _:
                raise RuntimeError("Unhandled data format")
    
        columns = np.array(values).reshape(1 + (2 * (port_count ** 2)), -1)
        frequencies = columns[0]
        s_params = columns[1:]

        # Swap position of S21/S12
        s_params[[2, 4]] = s_params[[4, 2]]
        s_params[[3, 5]] = s_params[[5, 3]]

        network = skrf.Network(f=frequencies)
        network.s = s_params.T.copy().reshape(-1,2,4).view(complex)
        return network

    # Format
    def set_byte_order(self, order):
        self.write(f":FORM:BORD {order}")

    def set_data_format(self, format):
        self.write(f":FORM {format}")
        self.data_format = format
    
    # Init
    def set_continuous(self, enable):
        self.write(f":INIT:CONT {int(enable)}")

    def immediate_trigger(self):
        self.write(f":INIT:IMM")
    
    # Memory
    def set_snp_store_format(self, format):
        self.write(f":MMEM:STOR:TRAC:FORM:SNP {format}")

    # Sense
    def set_correction_state(self, enable):
        self.write(f":SENS:CORR:STAT {int(enable)}")

    def get_cal_sets(self):
        names = self.read(f":SENS:CORR:CSET:CAT? NAME").split(",")
        guids = self.read(f":SENS:CORR:CSET:CAT? GUID").split(",")
        if len(names) != len(guids):
            raise RuntimeError("Mismatch between cal set names and GUIDs")
        return list(zip(names, guids))

    def activate_cal_set(self, name, apply_stimulus=True):
        self.write(f':SENS:CORR:CSET:ACT "{name}",{int(apply_stimulus)}')

    def create_cal_set(self, name):
        self.write(f':SENS:CORR:CSET:CREATE "{name}"')

    def delete_cal_set(self, guid):
        self.write(f':SENS:CORR:CSET:DELETE "{guid}"')

    def select_cal_set(self, name):
        self.write(f':SENS:CORR:CSET:NAME "{name}"')
    