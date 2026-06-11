from threading import Lock
from typing import Any, Dict


class SingletonMeta(type):
    __instances = {}
    __lock: Dict[Any, Lock] = {}

    def __call__(cls, *args, **kwargs):
        # Fix deadlock if a singleton class call another singleton class in __init__
        # (https://en.wikipedia.org/wiki/Double-checked_locking)
        if cls not in cls.__instances:
            if cls not in cls.__lock:
                cls.__lock[cls] = Lock()
            with cls.__lock[cls]:
                if cls not in cls.__instances:
                    cls.__instances[cls] = super(SingletonMeta, cls).__call__(*args, **kwargs)
        return cls.__instances[cls]

    # @classmethod
    # def instance(mcs, *args, **kwargs):
    #     with mcs.__lock:
    #         if mcs not in mcs.__instances:
    #             instance = super().__call__(*args, **kwargs)
    #             mcs.__instances[mcs] = instance
    #     return mcs.__instances[mcs]

# class SingletonMeta(object):
#     __instance = None
#
#     @classmethod
#     def __getInstance(cls):
#         return cls.__instance
#
#     @classmethod
#     def instance(cls, *args, **kwargs):
#         cls.__instance = cls(*args, **kwargs)
#         cls.instance = cls.__getInstance
#         return cls.__instance
