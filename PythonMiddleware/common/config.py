import os
from . import version as middleware_version
from .utils import get_abs_path, load_json
from .singleton_meta import SingletonMeta
from . import limits as Limits
from math import radians
import shutil

class ConfigLibrary(metaclass=SingletonMeta):
    DEPLOY_JSON_DEFAULT = 'indyDeploy.json'
    CONFIG_JSON_DEFAULT = 'configPath.json'
    CONTROL_TASK_BIN_DEFAULT = 'IndyControlTask'
    PROGRAM_DIR = ''
    ## SET DEFAULT PORTS FOR CLIENTS
    ETHERCAT_SOCKET_PORT = 20000
    CONTROL_SOCKET_PORT = 20001
    DEVICE_SOCKET_PORT = 20002
    CONFIG_SOCKET_PORT = 20003
    RTDE_SOCKET_PORT = 20004
    BOOT_SOCKET_PORT = 20010
    MOBY_SOCKET_PORT = 20200
    CONTY_SOCKET_PORT = 20131
    CRI_SOCKET_PORT = 20181
    LINEAR_SOCKET_PORT = 20300
    MOBY_V2_PORT = 50051
    LOG_PATH = get_abs_path("LogData/")
    SERVER_LOG_PATH = LOG_PATH + "Server/"

    SW_UPDATE_FILE_NAME = get_abs_path('indy_sw.zip')

    # deploy_json_abs = get_abs_path(DEPLOY_JSON_DEFAULT)
    # deploy_config = load_json(deploy_json_abs)
    # deploy_config

    ############################
    #    Exit Code             #
    ############################
    EXIT_NORMAL = 0
    EXIT_REBOOT = 1
    EXIT_UPDATE = 2
    EXIT_PW_OFF = 3

    ############################
    #    Vel Level Conversion  #
    ############################
    JogVelRatioMax = 25  # %
    VelAutoLevelValue = (Limits.VelRatioMax - JogVelRatioMax) / (Limits.LevelMax - Limits.JogLevelMax)  # %
    VelManualLevelValue = (JogVelRatioMax - Limits.JogVelRatioMin) / (Limits.JogLevelMax - Limits.JogLevelMin)  # %

    def __init__(self):
        self.VERSION_INFO = middleware_version.VERSION_INFO
        self.VERSION_DETAIL = middleware_version.VERSION_DETAIL
        self.VERSION_DATE = middleware_version.VERSION_DATE
        self.VERSION_MINIMUM = middleware_version.VERSION_MINIMUM

        ################################################################
        #    FIXED DIRECTORIES, NOT CONTROLLED BY JsonConfigManager    #
        ################################################################
        self.CONTROLLER_IP_ADDRESS = '127.0.0.1'
        self.LOG_PATH = get_abs_path("LogData/")
        self.SERVER_LOG_PATH = self.LOG_PATH + "Server/"

        self.DEPLOY_JSON = self.DEPLOY_JSON_DEFAULT
        self.CONFIG_JSON = self.CONFIG_JSON_DEFAULT
        self.CONTROL_TASK_BIN = self.CONTROL_TASK_BIN_DEFAULT

        self.PROGRAM_DIR = get_abs_path('ProgramScripts')
        self.INDEX_PROGRAM_DIR = self.PROGRAM_DIR + '/index'
        self.GCODE_DIR = get_abs_path('Gcodes')
        self.USE_AUTO_MODE = None


    ################################################################
    #    FILE CONFIG FUNCTIONS - FOR STAND-ALONE INITIALIZATION    #
    ################################################################

    def set_config_files(self,
                         deploy_json=DEPLOY_JSON_DEFAULT,
                         config_json=CONFIG_JSON_DEFAULT,
                         task_bin=CONTROL_TASK_BIN_DEFAULT):
        self.DEPLOY_JSON = deploy_json
        self.CONFIG_JSON = config_json
        self.CONTROL_TASK_BIN = task_bin


    ##
    # @return list of names of tasks of which binary file is task_bin
    def get_robot_tasks(self):
        deploy_json_abs = get_abs_path(self.DEPLOY_JSON)
        deploy_config = load_json(deploy_json_abs)
        task_names = []
        for task_name, task_config in deploy_config["RTTasks"].items():
            if self.CONTROL_TASK_BIN in task_name:
                task_names.append(task_name)
        return task_names

    def check_cobot(self):
        config_dict = load_json(get_abs_path(self.CONFIG_JSON))
        if config_dict is None:
            return True  # Cobot is used by default
        robot_configs = load_json(get_abs_path(config_dict["Config"]))
        if robot_configs is None:
            return True  # Cobot is used by default
        bot_type = "Cobot"
        if bot_type in robot_configs:
            return True
        return False

    def load_ports(self):
        deploy_json_abs = get_abs_path(self.DEPLOY_JSON)
        deploy_config = load_json(deploy_json_abs)
        task_order = deploy_config["RTTasks"][self.CONTROL_TASK_BIN]["Order"]

        config_dict = load_json(get_abs_path(self.CONFIG_JSON))
        port_config = None
        if "Ports" in config_dict:
            port_config = load_json(get_abs_path(config_dict["Ports"]))
        if port_config is None:
            port_config = {}
        self.ETHERCAT_SOCKET_PORT = port_config.get("EtherCAT", self.ETHERCAT_SOCKET_PORT)
        self.CONTROL_SOCKET_PORT = port_config.get("Control", [self.CONTROL_SOCKET_PORT])[task_order]
        self.DEVICE_SOCKET_PORT = port_config.get("Device", [self.DEVICE_SOCKET_PORT])[task_order]
        self.CONFIG_SOCKET_PORT = port_config.get("Config", [self.CONFIG_SOCKET_PORT])[task_order]
        self.RTDE_SOCKET_PORT = port_config.get("RTDE", [self.RTDE_SOCKET_PORT])[task_order]
        self.BOOT_SOCKET_PORT = port_config.get("Boot", [self.BOOT_SOCKET_PORT])[task_order]
        self.CRI_SOCKET_PORT = port_config.get("CRI", [self.CRI_SOCKET_PORT])[task_order]
        if "Moby" in port_config:
            self.MOBY_SOCKET_PORT = port_config.get("Moby", self.MOBY_SOCKET_PORT)
        if "Linear" in port_config:
            self.LINEAR_SOCKET_PORT = port_config.get("Linear", self.LINEAR_SOCKET_PORT)
        if "Conty" in port_config:
            self.CONTY_SOCKET_PORT = port_config.get("Conty", [self.CONTY_SOCKET_PORT])[task_order]

    def check_moby_v2_bridge(self):
        config_dict = load_json(get_abs_path(self.CONFIG_JSON))
        robot_configs = load_json(get_abs_path(config_dict["Config"]))

        mobile_key = "MobileRobot"
        bridge_key = "use_v2_bridge"
        use_bridge = False
        if mobile_key in robot_configs:
            mobile_config = robot_configs[mobile_key]
            if bridge_key in mobile_config:
                use_bridge = mobile_config[bridge_key]
        return use_bridge

    ##################################################################
    #    NON-FILE CONFIGURATION - FOR CONCRETE SYNC WITH FRAMEWORK   #
    ##################################################################
    def configure_robot(self, robot_name, robot_dof):
        self.ROBOT_NAME = robot_name
        self.ROBOT_MODEL = f"NRMK-{robot_name}"
        self.ROBOT_DOF = robot_dof

    def configure_controller(self, use_safety_io, use_npad, use_indykey, use_auto_mode):
        self.USE_SAFETYIO = use_safety_io
        self.USE_NPAD = use_npad
        self.USE_INDYKEY = use_indykey
        self.USE_AUTO_MODE = use_auto_mode

    ##
    # @param reuced_ratio 0~100, percent value
    def configure_conversion(self, reduced_ratio):
        self.reducedRatio = reduced_ratio
        self.JogVelRatioMax = self.reducedRatio
        self.VelAutoLevelValue = (Limits.VelRatioMax - self.JogVelRatioMax) / (Limits.LevelMax - Limits.JogLevelMax)  # %
        self.VelManualLevelValue = (self.JogVelRatioMax - Limits.JogVelRatioMin) / (Limits.JogLevelMax - Limits.JogLevelMin)  # %

    def configure_path(self, config_path, safety_path_list):
        self.ROBOT_CONFIG_PATH = get_abs_path(config_path)
        self.SAFETY_PATH_LIST = list(map(get_abs_path, safety_path_list))
        self.PALLET_MAKER_DIR = os.path.join(self.ROBOT_CONFIG_PATH, "Pallet.json")
        self.patch()

    def patch(self):
        # TODO: read old version and patch based on the version
        #       (for example, if some old file was deprecated already in the previous version, you may ignore that file)
        if not os.path.isfile(self.PALLET_MAKER_DIR):
            PALLET_MAKER_DIR_OLD = os.path.join(os.path.dirname(self.ROBOT_CONFIG_PATH), "Params", "Pallet.json")
            if os.path.isfile(PALLET_MAKER_DIR_OLD):
                shutil.copy2(PALLET_MAKER_DIR_OLD, self.PALLET_MAKER_DIR)
        # TODO: write current version when patch finished



    #############################
    #    CONVERSION FUCNTIONS   #
    #############################
    def to_vel_ratio(self, level):
        if level < Limits.LevelMin:
            level = Limits.LevelMin
        if level > Limits.LevelMax:
            level = Limits.LevelMax

        if level > Limits.JogLevelMax:
            vel_ratio = self.JogVelRatioMax + self.VelAutoLevelValue * (level - Limits.JogLevelMax)
        else:
            vel_ratio = Limits.JogVelRatioMin + self.VelManualLevelValue * (level - Limits.JogLevelMin)
        return vel_ratio

    def to_acc_ratio(self, level):
        if level < Limits.LevelMin:
            level = Limits.LevelMin
        if level > Limits.LevelMax:
            level = Limits.LevelMax
        acc_ratio = Limits.JogAccRatioDefault * level
        return acc_ratio
