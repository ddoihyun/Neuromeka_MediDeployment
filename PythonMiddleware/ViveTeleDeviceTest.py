from interfaces.teleop_server_vive import *


server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
servicer = TeleOpDeviceServicer()
teleop_grpc.add_TeleOpDeviceServicer_to_server(servicer=servicer, server=server)

server.add_insecure_port('[::]:{}'.format(DEVICE_PORT))
server.start()

server.wait_for_termination()
