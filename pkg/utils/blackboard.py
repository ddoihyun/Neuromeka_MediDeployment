import time
import json
import py_trees

from .file_io import load_json
from .logging import Logger
from .singleton import SingletonMeta

BB_CONFIG_DEFAULT_PATH = 'modules/blackboard.json'



def initialize_blackboard_from_json(board, json_file_path):
    board.clear()
    data = load_json(json_file_path)
    for key, value in data.items():
        if isinstance(value, str) and value.startswith("$"):  # string starts with $ is a runtime script
            board.set(key, eval(value[1:]))
        else:
            board.set(key, value)
    Logger.info(f"Blackboard initialized from {json_file_path}")


class GlobalBlackboard(py_trees.blackboard.Blackboard, metaclass=SingletonMeta):
    def __init__(self, json_file_path=BB_CONFIG_DEFAULT_PATH):
        super().__init__()
        initialize_blackboard_from_json(self, json_file_path)
