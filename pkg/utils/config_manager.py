import json
from pathlib import Path


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "app" / "default_app_config.json"


class ConfigManager:
    def __init__(self, config_path=DEFAULT_CONFIG_PATH):
        self.config_path = config_path
        self._config = {}
        self.load_config()

    def load_config(self, config_path=None):
        if config_path is None:
            config_path = self.config_path
        else:
            self.config_path = config_path

        with open(config_path, 'r') as file:
            self._config = json.load(file)

    def save_config(self, config_path=None):
        if config_path is None:
            config_path = self.config_path
        else:
            self.config_path = config_path

        with open(config_path, "w") as json_file:
            json.dump(self._config, json_file)

    def get(self, key, default=None):
        return self._config.get(key, default)

    def set(self, key, value):
        self._config[key] = value

    def delete(self, key):
        del self._config[key]
