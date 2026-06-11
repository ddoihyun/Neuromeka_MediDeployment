import os
import time
import numpy as np
import collections

import datetime

from enum import Enum


##
# @class TextColors
# @brief color codes for terminal. use println to simply print colored message
class TextColors(Enum):
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

    def println(self, msg):
        print(self.value + str(msg) + self.ENDC.value)

    def text(self, msg):
        return self.value + str(msg) + self.ENDC.value


def get_now():
    return str(datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))


##
# @class    Singleton
# @brief    Template to make a singleton class.
# @remark   Inherit this class to make a class a singleton.
#           Do not call the class constructor directly, but call <class name>.instance() to get singleton instance.
class GlobalSingleton:
    __instance = None

    @classmethod
    def __getInstance(cls):
        return cls.__instance

    @classmethod
    def instance(cls, *args, **kargs):
        cls.__instance = cls(*args, **kargs)
        cls.instance = cls.__getInstance
        return cls.__instance


##
# @class    GlobalTimer
# @brief    A singleton timer to record timings anywhere in the code.
# @remark   Call GlobalTimer.instance() to get the singleton timer.
#           To see the recorded times, just print the timer: print(global_timer)
# @param    scale       scale of the timer compared to a second. For ms timer, 1000
# @param    timeunit    name of time unit for printing the log
# @param    stack   default value for "stack" in toc
class GlobalTimer(GlobalSingleton):
    def __init__(self, scale=1000, timeunit='ms', stack=False):
        self.reset(scale, timeunit, stack)

    ##
    # @brief    reset the timer.
    # @param    scale       scale of the timer compared to a second. For ms timer, 1000
    # @param    timeunit    name of time unit for printing the log
    # @param    stack   default value for "stack" in toc
    def reset(self, scale=1000, timeunit='ms', stack=False):
        self.stack = stack
        self.scale = scale
        self.timeunit = timeunit
        self.name_list = []
        self.ts_dict = {}
        self.time_dict = collections.defaultdict(lambda: 0)
        self.min_time_dict = collections.defaultdict(lambda: 1e10)
        self.max_time_dict = collections.defaultdict(lambda: 0)
        self.count_dict = collections.defaultdict(lambda: 0)
        self.timelist_dict = collections.defaultdict(list)
        self.switch(True)

    def reset_key(self, name):
        if name in self.name_list:
            self.time_dict[name] = 0
            self.min_time_dict[name] = 1e10
            self.max_time_dict[name] = 0
            self.count_dict[name] = 0
            self.timelist_dict[name].clear()
            self.name_list.remove(name)

    ##
    # @brief    switch for recording time. switch-off to prevent time recording for optimal performance
    def switch(self, onoff):
        self.__on = onoff

    ##
    # @brief    mark starting point of time record
    # @param    name    name of the section to record time.
    def tic(self, name):
        if self.__on:
            if name not in self.name_list:
                self.name_list.append(name)
            self.ts_dict[name] = time.time()

    ##
    # @brief    record the time passed from last call of tic with same name
    # @param    name    name of the section to record time
    # @param    stack   to stack each time duration to timelist_dict, set this value to True,
    #                   don't set this value to use default setting
    def toc(self, name, stack=None):
        if self.__on:
            dt = (time.time() - self.ts_dict[name]) * self.scale
            self.time_dict[name] = self.time_dict[name] + dt
            self.min_time_dict[name] = min(self.min_time_dict[name], dt)
            self.max_time_dict[name] = max(self.max_time_dict[name], dt)
            self.count_dict[name] = self.count_dict[name] + 1
            if stack or (stack is None and self.stack):
                self.timelist_dict[name].append(dt)
            return dt

    ##
    # @brief    get current time and estimated time arrival
    # @param    name    name of the section to record time
    # @param    current current index recommanded to start from 1
    # @param    end     last index
    # @return   (current time, eta)
    def eta(self, name, current, end):
        dt = self.toc(name, stack=False)
        return dt, (dt / current * end if current != 0 else 0)

    ##
    # @brief    record and start next timer in a line.
    def toctic(self, name_toc, name_tic, stack=None):
        dt = self.toc(name_toc, stack=stack)
        self.tic(name_tic)
        return dt

    ##
    # @brief you can just print the timer instance to see the record
    def __str__(self):
        strout = ""
        names = self.name_list
        for name in names:
            strout += "{name}: \t{tot_T} {timeunit}/{tot_C} = {per_T} {timeunit} ({minT}/{maxT})\n".format(
                name=name, tot_T=np.round(np.sum(self.time_dict[name])), tot_C=self.count_dict[name],
                per_T=np.round(np.sum(self.time_dict[name]) / self.count_dict[name], 3),
                timeunit=self.timeunit, minT=round(self.min_time_dict[name], 3), maxT=round(self.max_time_dict[name], 3)
            )
        return strout

    ##
    # @brief use "with timer:" to easily record duration of a code block
    def block(self, key, stack=None, print_reset=False):
        return BlockTimer(self, key, stack=stack, print_reset=print_reset)

    def __enter__(self):
        self.tic("block")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.toc("block")


##
# @class    BlockTimer
# @brief    Wrapper class to record timing of a code block.
class BlockTimer:
    def __init__(self, gtimer, key, stack=None, print_reset=False):
        self.gtimer, self.key, self.stack, self.print_reset = gtimer, key, stack, print_reset

    def __enter__(self):
        self.gtimer.tic(self.key)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        dt = self.gtimer.toc(self.key, stack=self.stack)
        if self.print_reset:
            print(f"Block {self.key} {dt:.2f} {self.gtimer.timeunit}")
            self.gtimer.reset_key(self.key)
