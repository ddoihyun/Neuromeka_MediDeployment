import signal
import time
import platform
import sys
import os
# import keyboard



from modules.robot.robot_control import RobotCommunication
from modules.system.sysem_manager import SystemManager
from modules.system.system_fsm.context import SystemContext
from modules.system.system_fsm.fsm import SystemFsmSequence

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_MIDDLEWARE_PATH = os.path.join(BASE_DIR, "PythonMiddleware")
sys.path.insert(0, PYTHON_MIDDLEWARE_PATH)

from modules.global_data import Use_Joystick, Use_Voice
from modules.global_vars import joystick_manager, voice_manager
from modules.global_func import get_time
from modules.backend.backend_manager import BackendManager


from pkg.utils.blackboard import GlobalBlackboard
from pkg.utils.logging import Logger, LogLevel

lockfile = None
def lock_execution(lockfile_dir: str):
    """중복 실행 방지용 Lock 파일 생성."""
    global lockfile
    if os.name == "posix" and platform.system() == "Linux":
        import fcntl
        try:
            lockfile = open(lockfile_dir, "w")
            fcntl.lockf(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return lockfile
        except IOError:
            Logger.error(f"{get_time()}: another instance is running")
            sys.exit(1)
    else:
        return None

def sig_handler(signum, frame):
    """종료 시 실행할 정리 작업."""
    Logger.info(f"{get_time()}: Signal {signum} received, shutting down...")
    pass # 종료 시 실행할 명령

    # Lock 파일 해제
    if lockfile is not None:
        try:
            lockfile.close()
        except Exception as e:
            Logger.error(f"Failed to close lockfile: {e}")

    sys.exit(0)

def setup_signal_handlers():
    """SIGINT/SIGTERM 핸들러 등록."""
    signal.signal(signal.SIGTERM, sig_handler)
    signal.signal(signal.SIGINT, sig_handler)

if __name__ == '__main__':
    Logger.set_log_level(LogLevel.DEBUG)  # DEBUG INFO WARN ERROR
 
    lockfile = lock_execution("/tmp/fsm.lock")
    setup_signal_handlers()

    bb = GlobalBlackboard()

    backend = BackendManager()
    backend.start()
    time.sleep(0.1)

    # keyboard.on_press_key("space", lambda _: on_space())
    if Use_Voice and voice_manager is not None:
        voice_manager.start()
    if Use_Joystick:
        joystick_manager.start()
    else:
        bb.set("joystick/state/connect", True)
    
    ''' FSM thread '''
    system_context = SystemContext()
    system_fsm = SystemFsmSequence(system_context)
    system_fsm.start_service_background()

    # ''' Robot thread '''
    robot = RobotCommunication()

    Logger.info(f"{get_time()}: Robot Started") # 로봇을 가장 나중에 둬야 다른 쓰레드에서 확인할 수 있지

    Logger.debug(f"{get_time()}: [System] Started")

    system_manger = SystemManager()
    system_manger.start()

    while True:
        # print(bb.get("joystick/state/connect"))
        # time.sleep(1)
        # Controller (Xbox One For Windows)
        if True:
            time.sleep(0.01)
            if Use_Joystick:
                joystick_manager.poll_inputs()
            else:
                bb.set("joystick/state/connect", True)

        else:
            Logger.error(f"{get_time()}: Error, shutting down.")
            sig_handler(signal.SIGTERM, None)  # 강제로 종료

