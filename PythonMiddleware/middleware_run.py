import sys
import os

import signal
import sys
import grpc
from time import sleep
from concurrent import futures
import json

import common as Common
import logging
import argparse

from config_updater import ConfigUpdater, install_and_reboot
from bbb_updater import update_bbb, UPDATE_FILE_DEFAULT

PYTHON_MIDDLEWARE_DIR = os.path.dirname(os.path.abspath(__file__))
DEPLOYMENT_DIR = os.path.abspath(os.path.join(PYTHON_MIDDLEWARE_DIR, os.pardir))

parser = argparse.ArgumentParser(description='Indy Middleware')
parser.add_argument('-c', '--config', required=False, type=str,
                    default=Common.Config.CONFIG_JSON_DEFAULT,
                    help=f"Configuration File (default: {Common.Config.CONFIG_JSON_DEFAULT})")
parser.add_argument('-j', '--json', required=False, type=str,
                    default=Common.Config.DEPLOY_JSON_DEFAULT,
                    help=f"Deployment Json File (default: {Common.Config.DEPLOY_JSON_DEFAULT})")
parser.add_argument('-t', '--task', required=False, type=str,
                    default=Common.Config.CONTROL_TASK_BIN_DEFAULT,
                    help=f"Contol Task Binary Name (default: {Common.Config.CONTROL_TASK_BIN_DEFAULT})")
parser.add_argument('-d', '--debug', required=False, action='store_true',
                    default=False, help=f"set log level to DEBUG")
args = parser.parse_args()

config = Common.Config()
config.set_config_files(args.json, args.config, args.task)
config.load_ports()

## Update when middleware starts, for Conty-update scenario
updater = ConfigUpdater(Common.Config().VERSION_INFO, args.json)
if updater.check_and_update():
    updater.update_kill_tasks()
    print("Reboot to finish update update")
    if os.path.isfile(UPDATE_FILE_DEFAULT):
        update_bbb(UPDATE_FILE_DEFAULT, args.config)
    install_and_reboot()
else:
    updater.update_kill_tasks()

from managers.log_manager import LogManager
if args.debug:
    LogManager().set_log_level(level=logging.DEBUG)

MIDDLEWARE_RUN = True

import interfaces as SocketInf

# from ext_parties.modbus_manager import ModbusManager
# from indy_dcp.dcp_server import DcpServicer


############################
# Termination
############################
def sig_handler(signum, frame):
    print('Middleware: SIGNAL RECEIVED:', signum)
    global MIDDLEWARE_RUN
    MIDDLEWARE_RUN = False

signal.signal(signal.SIGTERM, sig_handler)
signal.signal(signal.SIGINT, sig_handler)

############################
# Main
############################
if __name__ == "__main__":    
    # gRPC Clients
    local_host = Common.Config().CONTROLLER_IP_ADDRESS
    boot_client = SocketInf.BootClient(local_host, Common.Config().BOOT_SOCKET_PORT)
    control_client = SocketInf.ControlClient(local_host, Common.Config().CONTROL_SOCKET_PORT)
    config_client = SocketInf.ConfigClient(local_host, Common.Config().CONFIG_SOCKET_PORT)
    device_client = SocketInf.DeviceClient(local_host, Common.Config().DEVICE_SOCKET_PORT)
    rtde_client = SocketInf.RTDEClient(local_host, Common.Config().RTDE_SOCKET_PORT)
    ecat_client = SocketInf.EcatClient(local_host, Common.Config().ETHERCAT_SOCKET_PORT)
    cri_client = SocketInf.CRIClient(local_host, Common.Config().CRI_SOCKET_PORT)


    # External Axes gRPC Client
    linear_client = SocketInf.LinearClient(local_host, Common.Config().LINEAR_SOCKET_PORT)

    # gRPC Server
    middleware_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10),
                                    options=
                                    [('grpc.max_send_message_length', 16 * 1024 * 1024),
                                     ('grpc.max_receive_message_length', 16 * 1024 * 1024)]
                                    )

    bridge_server, bridge_servicer = None, None
    if config.check_moby_v2_bridge():
        from interfaces.moby_bridge_servicer import serve_moby_bridge
        print("Run V2 bridge server")
        bridge_server, bridge_servicer = serve_moby_bridge(port=config.MOBY_V2_PORT, ecat_port=config.ETHERCAT_SOCKET_PORT, moby_port=config.MOBY_SOCKET_PORT)

    # Conty Servicer
    conty_servicer = SocketInf.ContyServicer(boot_client=boot_client,
                                             device_client=device_client,
                                             config_client=config_client,
                                             control_client=control_client,
                                             rtde_client=rtde_client,
                                             ecat_client=ecat_client,
                                             linear_client=linear_client,
                                             cri_client = cri_client)
    SocketInf.add_HRIServicer_to_server(servicer=conty_servicer, server=middleware_server)

    middleware_server.add_insecure_port('[::]:{}'.format(Common.Config().CONTY_SOCKET_PORT))
    middleware_server.start()

    dcp_server = SocketInf.IndyDCP(boot_client=boot_client,
                                   device_client=device_client,
                                   config_client=config_client,
                                   control_client=control_client,
                                   rtde_client=rtde_client,
                                   ecat_client=ecat_client,
                                   linear_client=linear_client)
    dcp_server.startServer()

    exit_code = Common.Config.EXIT_NORMAL
    while MIDDLEWARE_RUN:
        if conty_servicer.is_reboot():
            print('Reboot Request')
            exit_code = Common.Config.EXIT_REBOOT
            break
        if conty_servicer.is_power_off():
            print('PowerOff Request')
            exit_code = Common.Config.EXIT_PW_OFF
            break
        if conty_servicer.is_update():
            print('Update Request')            
            exit_code = Common.Config.EXIT_UPDATE
            break
        sleep(0.2)

    dcp_server.stopServer()
    conty_servicer.stop()
    middleware_server.stop(grace=3)

    middleware_server.wait_for_termination()
    print('Middle ended')

    if bridge_server is not None:
        bridge_server.stop(grace=3)
        bridge_server.wait_for_termination()
        print('Bridge ended')

    sys.exit(exit_code)
