import os
import sys
import threading
import time
import subprocess

from .log_manager import LogManager
import common as Common


class HRIManager(metaclass=Common.SingletonMeta):
    CONTY_TAG = 'Conty'
    KEY_TAG = 'Key'

    def __init__(self) -> None:
        super().__init__()
        self._logger = LogManager()
        self._devices = []

        self._working = False
        if sys.platform == 'linux':
            self._usb_thread = threading.Thread(target=self._run_usb_monitoring)
            self.enable_usb_connection()
        else:
            self._log_warn('USB Connection is not supported')
            self._usb_thread = None

    def __del__(self):
        self._working = False

    def enable_usb_connection(self):
        if self._usb_thread is not None:
            self._working = True
            self._usb_thread.start()

    def disable_usb_connection(self):
        if self._usb_thread is not None:
            self._working = False
            self._usb_thread.join()

    def has_conty(self) -> bool:
        return self.CONTY_TAG in self._devices

    def update_conty(self, connected: bool) -> bool:
        success = False
        if connected:
            if self.CONTY_TAG not in self._devices:
                self._devices.append(self.CONTY_TAG)
                success = True
                self._log_info('Conty was registered successfully')
            else:
                self._log_error('Conty was already registered')
        else:
            if self.CONTY_TAG in self._devices:
                self._devices.remove(self.CONTY_TAG)
                success = True
                self._log_info('Conty was removed successfully')
            else:
                self._log_error('Conty has not been registered yet')

        return success

    def _run_usb_monitoring(self):
        subprocess.check_output(['adb', 'start-server'])

        def find_device():
            devices = subprocess.check_output(['adb', 'devices', '-l']).decode("utf-8")
            for d in devices.split("\n"):
                if "device usb" in d:
                    return True
            return False

        usb_connected = False
        while self._working:
            if not usb_connected:
                if find_device():
                    subprocess.check_output(['adb', 'reverse', 'tcp:20131', 'tcp:20131'])
                    subprocess.check_output(['adb', 'reverse', 'tcp:8022', 'tcp:22'])
                    subprocess.check_output(['adb', 'reverse', 'tcp:8088', 'tcp:8088'])  # for indyeye
                    subprocess.check_output(['adb', 'reverse', 'tcp:9000', 'tcp:9000'])  # for rest server
                    usb_connected = True
                    self._log_info('USB is connected !')
            else:
                if not find_device():
                    self._log_info('USB is disconnected !')
                    usb_connected = False
            time.sleep(3.0)
        subprocess.check_output(['adb', 'kill-server'])
        os.system('killall -9 adb')

    def _log_info(self, content=''):
        self._logger.info(content=content, source='HRIManager')

    def _log_warn(self, content='', source=''):
        self._logger.warn(content=content, source='HRIManager')

    def _log_error(self, content='', source=''):
        self._logger.error(content=content, source='HRIManager')
