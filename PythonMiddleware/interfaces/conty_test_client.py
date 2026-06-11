 ## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect
import os
import sys
impl_path = os.path.join(os.path.dirname(__file__), 'impl')
sys.path.append(impl_path)

from google.protobuf import json_format


import common_msgs_pb2 as common_data
import hri_msgs_pb2 as conty_data
import hri_pb2_grpc as conty_grpc
import config_msgs_pb2 as config_data
import config_pb2_grpc as config_grpc

import time
import grpc
import common as Common
import managers as Managers

 


class ContySocketClient(metaclass=Common.SingletonMeta):
    def __init__(self, ip_addr, port=Common.Config().CONTY_SOCKET_PORT):
        conty_channel = grpc.insecure_channel("{}:{}".format(ip_addr, port))
        conty_stub = conty_grpc.HRIStub(conty_channel)
        config_channel = grpc.insecure_channel("{}:{}".format(ip_addr, Common.Config().CONFIG_SOCKET_PORT))
        config_stub = config_grpc.ConfigStub(config_channel)
        self.__conty_stub = Common.Utils.StubWithTimeout(stub=conty_stub, timeout=Common.Limits.GRPCTimeOut)
        self.__config_stub = Common.Utils.StubWithTimeout(stub=config_stub, timeout=Common.Limits.GRPCTimeOut)
        self.__token = None
        self.__metadata = []
 
    @Common.Utils.exception_handler
    def ContyInit(self):
        response = self.__conty_stub.ContyInit(conty_data.ContyInitReq())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)
    def _headers(self):
        return self.__metadata if self.__metadata else None
    @Common.Utils.exception_handler
    def Login(self, digest: str):
        response = self.__conty_stub.Login(config_data.Digest(digest=digest))
        self.__token = response.token
        self.__metadata = [("authorization", f"Bearer {self.__token}")]
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)
    @Common.Utils.exception_handler
    def GetNonce(self):
        response = self.__conty_stub.GetNonce(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True) 
    @Common.Utils.exception_handler
    def LoginWithPassword(self, password: str):
        # 1) nonce 갱신
        self.__conty_stub.GetNonce(common_data.Empty())
 
        # 2) 현재 nonce 기준 digest 생성
        digest_res = self.__config_stub.TestDigest(config_data.Passwd(passwd=password))
 
        # 3) login
        response = self.__conty_stub.Login(config_data.Digest(digest=digest_res.digest))
        self.__token = response.token
        self.__metadata = [("authorization", f"Bearer {self.__token}")]
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)
 

    @Common.Utils.exception_handler
    def PingFromConty(self):
        response = self.__conty_stub.PingFromConty(common_data.Empty(),metadata=self._headers())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)