from datetime import datetime
from pathlib import Path

from pkg.utils.blackboard import GlobalBlackboard
from pkg.utils.logging import Logger
from pkg.utils.file_io import load_json

bb = GlobalBlackboard()


def get_time():
    return datetime.now().strftime("%H:%M:%S")


def get_intvar_address(int_var, addr):
    return next((int(item['value']) for item in int_var if item['addr'] == addr), None)


def get_dio_channel(di, ch):
    return next((int(item['state']) for item in di if item['address'] == ch), None)


def get_di(data, address):
    try:
        datav = data[0]['states'][address]
        return datav
    except:
        return None



def _is_feature_enabled(key: str, default: bool = False) -> bool:
    config_path = Path(__file__).resolve().parent.parent / "configs" / "function_flags.json"
    try:
        flags = load_json(str(config_path))
    except Exception:
        Logger.warn(f"{get_time()}: [GLOBAL] Failed to load {config_path}. Using default for '{key}'")
        return default

    value = flags.get(key, default)
    return bool(value)
