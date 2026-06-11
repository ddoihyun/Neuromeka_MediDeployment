from dataclasses import dataclass


@dataclass
class VarList:
    name: str
    address: int
    type: str  # SignalType


@dataclass
class ModbusServer:
    server_name: str
    ip: str
    port: int
    variable_list: list  # list of VarList


class SignalType:
    READ_COIL = 0
    WRITE_COIL = 1
    READ_REGISTER = 2
    WRITE_REGISTER = 3
