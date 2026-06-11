import time

from pyModbusTCP.client import ModbusClient

modbus_client = ModbusClient(host='127.0.0.1', port=502, auto_open=True, auto_close=True, debug=False)

# read 10 registers at address 0, store result in regs list
regs_l = modbus_client.read_holding_registers(0, 10)
# if success display registers
if regs_l:
    print('reg ad #0 to 9: %s' % regs_l)
else:
    print('unable to read registers')

modbus_client.write_single_register(0, 13)
modbus_client.write_single_register(1, 14)
modbus_client.write_single_register(2, 15)
modbus_client.write_single_register(3, 16)
modbus_client.write_single_register(4, 17)
modbus_client.write_single_register(5, 18)
modbus_client.write_single_register(6, 18)
modbus_client.write_single_register(7, 18)
modbus_client.write_single_register(8, 18)
modbus_client.write_single_register(9, 18)
modbus_client.write_single_register(10, 18)

for ad in range(4):
    is_ok = modbus_client.write_single_coil(ad, True)
    if is_ok:
        print('coil #%s: write to %s' % (ad, True))
    else:
        print('coil #%s: unable to write %s' % (ad, True))
    time.sleep(0.5)

# read 10 registers at address 0, store result in regs list
regs_l = modbus_client.read_holding_registers(0, 10)
# if success display registers
if regs_l:
    print('reg ad #0 to 9: %s' % regs_l)
else:
    print('unable to read registers')


modbus_client.write_single_coil(1163, 1)
modbus_client.write_single_coil(1163, 0)