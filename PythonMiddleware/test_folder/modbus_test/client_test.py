import time

from pyModbusTCP.client import ModbusClient

modbus_client = ModbusClient(host='192.168.1.6', port=502, auto_open=True, debug=False)

# read 10 bits (= coils) at address 0, store result in coils list
coils_l = modbus_client.read_coils(0, 10)

# if success display registers
if coils_l:
    print('coil ad #0 to 9: %s' % (coils_l))
else:
    print('unable to read coils')

# read 10 registers at address 0, store result in regs list
regs_l = modbus_client.read_holding_registers(0, 10)

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

# if success display registers
if regs_l:
    print('reg ad #0 to 9: %s' % regs_l)
else:
    print('unable to read registers')
# sleep 2s before next polling
time.sleep(2)

print('write bits')
print('----------\n')
bit = True
for ad in range(4):
    is_ok = modbus_client.write_single_coil(ad, bit)
    if is_ok:
        print('coil #%s: write to %s' % (ad, bit))
    else:
        print('coil #%s: unable to write %s' % (ad, bit))
    time.sleep(0.5)
print('')
time.sleep(1)

# read 4 bits in modbus address 0 to 3
print('read bits')
print('---------\n')
bits = modbus_client.read_coils(0, 4)
if bits:
    print('coils #0 to 3: %s' % bits)
else:
    print('coils #0 to 3: unable to read')

# toggle
# bit = not bit
# sleep 2s before next polling
print('')
time.sleep(2)
