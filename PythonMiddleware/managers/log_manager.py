import os
import glob
import time
import datetime
import logging
import logging.handlers
from collections import deque

import common as Common


class LogManager(metaclass=Common.SingletonMeta):
    CHUNK_SIZE = 1024 * 1024  # 1 MB

    def __init__(self):
        pass
        # self._init_logger()
        # self._init_alarm()
        # self.remove_old_log()

    def _init_logger(self):
        self._logger = logging.getLogger('A.B.C')
        # self._logger.setLevel(logging.DEBUG)
        self._logger.setLevel(logging.INFO)

        formatter = logging.Formatter('[%(levelname)s] %(asctime)s, %(message)s')

        # console log 출력
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        self._logger.addHandler(stream_handler)

        os.makedirs(Common.Config().SERVER_LOG_PATH, exist_ok=True)

        log_file_name = '{}.log'.format(
            datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S"),
        )
        log_file_dir = os.path.join(Common.Config().SERVER_LOG_PATH, log_file_name)

        rotating_file_handler = logging.handlers.RotatingFileHandler(
            log_file_dir, maxBytes=10 * 1024 * 1024, backupCount=20
        )

        rotating_file_handler.setFormatter(formatter)
        self._logger.addHandler(rotating_file_handler)
        self._logger.info("Logger Started")

    def set_log_level(self, level):
        self._logger.setLevel(level)

    def _init_alarm(self):
        self._alarm_q = deque()

    def add_alarm(self, msg):
        self._alarm_q.append(msg)

    def get_alarm(self):
        if self._alarm_q:
            return self._alarm_q.popleft()
        else:
            return ''

    def info(self, content='', source=''):
        self._logger.info(source + ': ' + content)

    def debug(self, content='', source=''):
        self._logger.debug(source + ': ' + content)

    def warn(self, content='', source=''):
        self._logger.warning(source + ': ' + content)

    def error(self, content='', source=''):
        self._logger.error(source + ': ' + content)

    def remove_old_log(self, max_num=100):
        logfiles = glob.glob('{}*.log'.format(Common.Config().SERVER_LOG_PATH))
        logfiles.sort()
        if len(logfiles) > max_num:
            print("You have more than 100 log files. Attempt to remove.")
            try:
                remove_list = logfiles[:len(logfiles) - max_num]  # logfiles[:-max_num]
                for rm_dir in remove_list:
                    os.remove(rm_dir)

            except Exception as e:
                print(e)

    def get_log_list(self):
        logfiles = glob.glob('{}*.log'.format(Common.Config().SERVER_LOG_PATH))
        logfiles.sort()

        sizes = []
        modified_dates = []
        for f in logfiles:
            sizes.append(str(os.path.getsize(f) / 1024) + " KB")  # KB
            mtime = os.path.getmtime(f)
            modified_dates.append(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime)))

        return logfiles, sizes, modified_dates

    def get_log_file(self, file_name) -> {bool, bytes}:
        log_file_names, sizes, modified_dates = self.get_log_list()

        if file_name not in log_file_names:
            return False, bytes('File not found!', 'utf-8')

        log_content = bytes()  # bytearray()
        try:
            with open(file_name, 'rb') as file:
                while True:
                    piece = file.read(self.CHUNK_SIZE)
                    if len(piece) == 0:
                        break
                    log_content = log_content + piece
        except Exception as e:
            return False, bytes('File corrupted!', 'utf-8')

        return True, log_content

    def get_log_files(self, file_name_list) -> list:
        log_content_list = list()
        for log_name in file_name_list:
            res, log_content = self.get_log_file(log_name)
            log_content_list.append(log_content)

        return log_content_list


############################
# Main
############################
if __name__ == "__main__":
    log_manager = LogManager()
    # logfiles, sizes, modified_dates = log_manager.get_log_list()
    # print(logfiles)
    log_manager.info('A', 'Hi')
