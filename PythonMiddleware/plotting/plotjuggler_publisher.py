import signal
import struct
import sys
import os
import socket
import time
import argparse

import grpc
from google.protobuf import json_format

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + '\\..\\interfaces\\impl')

import interfaces.impl.common_msgs_pb2 as common_msgs
import interfaces.impl.plotting_pb2_grpc as plotting_servicer

PLOTTING_RUN = True


############################
# Termination
############################
def sig_handler(signum, frame):
    print('Plotting: SIGNAL RECEIVED:', signum)
    global PLOTTING_RUN
    PLOTTING_RUN = False


signal.signal(signal.SIGTERM, sig_handler)
signal.signal(signal.SIGINT, sig_handler)

############################
# Main
############################
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('ipaddr')
    args = parser.parse_args()
    plotter_ip = args.ipaddr

    sock = socket.socket(socket.AF_INET,  # Internet
                         socket.SOCK_DGRAM)  # UDP

    with grpc.insecure_channel("127.0.0.1:30001") as channel:
        stub = plotting_servicer.RTPlottingServiceStub(channel)

        for plotting_data in stub.GetPlottingData(common_msgs.Empty()):
            if not PLOTTING_RUN:
                break

            # rt_data_dict = json_format.MessageToDict(plotting_data,
            #                                          including_default_value_fields=True,
            #                                          preserving_proto_field_name=True,
            #                                          use_integers_for_enums=True)
            # print(plotting_data.time)
            # time.sleep(0.2)
            rt_data_json = json_format.MessageToJson(plotting_data,
                                                     including_default_value_fields=True,
                                                     preserving_proto_field_name=True,
                                                     use_integers_for_enums=True)
            sock.sendto(rt_data_json.encode(), (plotter_ip, 9870))
