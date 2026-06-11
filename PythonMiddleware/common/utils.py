import numpy as np
from math import *
import os
import json
import socket
import netifaces
from dataclasses import dataclass, field
from .jsmin import jsmin

import grpc
from . import limits as Limits


@dataclass
class GRPCReturn:
    code: grpc.StatusCode = grpc.StatusCode.OK
    details: str = ''

def exception_handler(func):
    def wrapper(self, *args, **kwargs):
        try:
            res = func(self, *args, **kwargs)
            wrapper.print_flag = True
            return res
        except grpc.RpcError as ex:
            if wrapper.print_flag:
                wrapper.print_flag = False
                # print('Function: ' + str(func.__name__) + ' received gRPC error: ' + str(ex))
                print('GRPC Exception at ' + str(func.__name__) + ' (' + str(ex.code()) + ' - ' + str(ex.details()) + ')')
            return None
    wrapper.print_flag = True

    return wrapper



def exception_forwarder(func):
    def wrapper(self, *args, **kwargs):
        try:
            res = func(self, *args, **kwargs)
            wrapper.print_flag = True
            return res
        except grpc.RpcError as ex:
            if wrapper.print_flag:
                wrapper.print_flag = False
                # print('Function: ' + str(func.__name__) + ' received gRPC error: ' + str(ex))
                print('GRPC Exception Forwarder at ' + str(func.__name__) + ' (' + str(ex.code()) + ' - ' + str(
                    ex.details()) + ')')
            return GRPCReturn(code=ex.code(), details=ex.details())
    wrapper.print_flag = True

    return wrapper

class StubWithTimeout:
    def __init__(self, stub, timeout):
        self._stub = stub
        self._timeout = timeout

    def __getattr__(self, name):
        method = getattr(self._stub, name)
        def wrapper(*args, **kwargs):
            kwargs.setdefault('timeout', self._timeout)
            return method(*args, **kwargs)
        return wrapper

# def get_ip():
#     s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#     s.connect(("8.8.8.8", 80))
#     r = s.getsockname()[0]
#     s.close()
#     return r

def get_ip():
    ip_addr = ''
    interfaces = netifaces.interfaces()
    for interface in interfaces:
        if interface != 'lo':
            ip = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in ip:
                ip_addr = ip[netifaces.AF_INET][0]['addr']
    return ip_addr


def get_all_ip():
    ip_list = []
    interfaces = netifaces.interfaces()
    for interface in interfaces:
        ip = netifaces.ifaddresses(interface)
        if netifaces.AF_INET in ip:
            ip_list.append(ip[netifaces.AF_INET][0]['addr'])
    return ip_list


def get_middleware_path():
    __common_dir = os.path.dirname(os.path.abspath(__file__))
    __middleware_dir = os.path.dirname(__common_dir)
    return __middleware_dir


def get_deploy_path():
    __deploy_dir = os.path.dirname(get_middleware_path())
    return __deploy_dir


##
# @brief convert to absolute path if path is relative (not start with '/')
def get_abs_path(path: str):
    if path.startswith("/"):
        return path
    else:
        return os.path.join(get_deploy_path(), path)


def write_json(file_name_abs, dict_obj):
    file_dir = os.path.dirname(file_name_abs)
    if not os.path.isdir(file_dir):
        os.makedirs(file_dir, exist_ok=True)
    with open(file_name_abs, 'w') as f:
        json.dump(dict_obj, f, indent=4)


def load_json(file_name_abs):
    def dupe_checking_hook(pairs):
        result = dict()
        for key, val in pairs:
            if key in result:
                raise KeyError("Duplicate key specified: %s" % key)
            result[key] = val
        return result

    if os.path.isfile(file_name_abs):
        with open(file_name_abs) as f:
            try:
                decoder = json.JSONDecoder(object_pairs_hook=dupe_checking_hook)
                json_min_raw = jsmin(f.read())
                data_dic = decoder.decode(json_min_raw)
            except Exception as e:
                print(f"Exception reading file {file_name_abs}:{e}")
                data_dic = None
            return data_dic
    else:
        return None


def rot_axis(axis, degree):
    th = radians(degree)
    if axis == 1:
        rot_matrix = np.asarray([[1, 0, 0], [0, cos(th), -sin(th)], [0, sin(th), cos(th)]])
    elif axis == 2:
        rot_matrix = np.asarray([[cos(th), 0, sin(th)], [0, 1, 0], [-sin(th), 0, cos(th)]])
    elif axis == 3:
        rot_matrix = np.asarray([[cos(th), -sin(th), 0], [sin(th), cos(th), 0], [0, 0, 1]])
    else:
        rot_matrix = np.identity
    return rot_matrix


def euler_to_rotm(uvw):
    rx = uvw[0]
    ry = uvw[1]
    rz = uvw[2]
    return np.matmul(np.matmul(rot_axis(3, rz), rot_axis(2, ry)), rot_axis(1, rx))


def rotm_to_euler(rot_matrix):
    sy = sqrt(rot_matrix[0, 0] ** 2 + rot_matrix[1, 0] ** 2)

    if sy > 0.000001:
        u = degrees(atan2(rot_matrix[2, 1], rot_matrix[2, 2]))
        v = degrees(atan2(-rot_matrix[2, 0], sy))
        w = degrees(atan2(rot_matrix[1, 0], rot_matrix[0, 0]))
    else:
        u = degrees(atan2(-rot_matrix[1, 2], rot_matrix[1, 1]))
        v = degrees(atan2(-rot_matrix[2, 0], sy))
        w = 0

    return np.asarray([u, v, w])


def pos_to_transform(p):
    xyz = p[:3]
    uvw = p[3:]
    transform_matrix = np.identity(4)
    transform_matrix[:3, :3] = euler_to_rotm(uvw)
    transform_matrix[:3, 3] = xyz[:]
    return transform_matrix


def transform_to_pos(transform_matrix):
    p = [0, 0, 0, 0, 0, 0]
    p[:3] = transform_matrix[:3, 3]
    p[3:] = list(rotm_to_euler(transform_matrix[:3, :3]))
    return p

# def to_task_vel(level):
#     """
#     Params:
#         | level: 1 ~ 9
#     Return:
#         | disp_vel = level x 25 mm
#         | rot_vel = level x 10 deg
#     """
#     if level < 1:
#         level = 1
#     if level > 9:
#         level = 9
#
#     disp_vel = common.VelTaskDispMin + common.VelTaskDispDiff*(level-1)
#     rot_vel = common.VelTaskRotMin + common.VelTaskRotDiff*(level-1)
#
#     # disp_vel = level * 25
#     # rot_vel = level * 10
#
#     return disp_vel, rot_vel


# def to_task_acc(level, disp_vel, rot_vel):
#     """
#     Params:
#         | level: 1 ~ 9
#         | disp_vel: mm
#         | rot_vel: deg
#     Return:
#         | disp_acc = level x disp_vel
#         | rot_acc = level x rot_vel
#     """
#     if level < 1:
#         level = 1
#     if level > 9:
#         level = 9
#
#     disp_acc = level * disp_vel
#     rot_acc = level * rot_vel
#     return disp_acc, rot_acc


import traceback
def try_wrap(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            traceback.print_exc()
            return None
    return wrapper


