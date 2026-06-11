import sys
import os

from ..base import ModbusStyleClientBase

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_dir, "grpc_gen"))

import grpc
from . import template_pb2_grpc
from .template_pb2 import GInt, IntVal, GInts,IntVals, Empty
import time


class gRPC_Client(ModbusStyleClientBase):
    client: template_pb2_grpc.GRPCGlobalVariableTaskStub

    # def __init__(self, ip, port):
    #     self.channel_name = f"{ip}:{port}"
    #     self.channel = None
    #     self.connect()  # Make one connection attempt
    #
    # def connect(self):
    #     # Close the existing channel before creating a new one
    #     if self.channel is not None:
    #         self.channel.close()
    #
    #     self.channel = grpc.insecure_channel(self.channel_name)
    #     self.client = template_pb2_grpc.GRPCGlobalVariableTaskStub(self.channel)
    #
    # def disconnect(self):
    #     if self.channel:
    #         self.channel.close()
    #
    # # ... rest of your methods ...
    #
    # def check_reopen(self) -> bool:
    #     try:
    #         grpc.channel_ready_future(self.channel).result(timeout=0.5)
    #         return True
    #     except grpc.FutureTimeoutError:
    #         print("GRPCGlobalVariableTaskStub Channel Timeout Error - Trying to Reconnect")
    #         self.reconnect()
    #         return False
    #     except Exception as e:
    #         print("GRPCGlobalVariableTaskStub Channel Unexpected Error - Trying to Reconnect")
    #         print(e)
    #         self.reconnect()
    #         return False
    #
    # def reconnect(self):
    #     self.disconnect()  # Ensure the current channel is closed
    #     time.sleep(1)  # Wait a bit before attempting to reconnect
    #     self.connect()

    def __init__(self, ip, port):
        self.channel_name = ip + ":"+ str(port)
        self.channel = None
        while True:
            self.connect()
            if self.check_reopen():
                print("GRPCGlobalVariableTaskStub channel is ready for communication.")
                break

    def connect(self):
        self.channel = grpc.insecure_channel(self.channel_name)  # 서버 주소 및 포트를 적절하게 지정
        self.client = template_pb2_grpc.GRPCGlobalVariableTaskStub(self.channel)

    def disconnect(self):
        self.channel.close()


    def check_reopen(self) -> bool:
        try:
            grpc.channel_ready_future(self.channel).result(timeout=0.5)
            return True
        except grpc.FutureTimeoutError:
            print("GRPCGlobalVariableTaskStub Channel Timeout Error - Try Reconnection")
            try:
                self.disconnect()
                self.connect()
            finally:
                return False
        except Exception as e:
            print("GRPCGlobalVariableTaskStub Channel Unexpected Error - Try Reconnection")
            print(e)
            try:
                self.disconnect()
                self.connect()
            finally:
                return False

    def set_int(self, idx, val):
        request = GInt(idx=idx, val=val)  # 요청 객체 생성 및 데이터 설정
        response = self.client.SetInt(request)
        
    def set_ints(self, idx, val):
        request = GInts(idx=idx, val=val)  # 요청 객체 생성 및 데이터 설정
        response = self.client.SetInts(request)
        
    def get_int(self, idx):
        request = IntVal(val=idx)  # 요청 객체 생성 및 데이터 설정
        response = self.client.GetInt(request)
        return response.val
    
    def get_ints(self, idx, count):
            request = GInt(idx=idx, val=count)  # 요청 객체 생성 및 데이터 설정
            response = self.client.GetInts(request)
            return response.val



