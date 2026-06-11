from dataclasses import dataclass


DEFAULT_COLLISION_GAIN_BASE = 500.0

class CollisionPolicyType:
    NONE = -1  # common_data.COLL_NO_DETECT
    NO_DETECT = 0  # common_data.COLL_NO_DETECT
    PAUSE = 1  # common_data.COLL_PAUSE
    RESUME_AFTER_SLEEP = 2  # common_data.COLL_RESUME_AFTER_SLEEP
    STOP = 3  # common_data.COLL_STOP


@dataclass
class CollisionConfig:
    policy: CollisionPolicyType = CollisionPolicyType.PAUSE
    sleep_time: int = 5


class TuningPrecision:
    LOW = 0  # config_data.CollTuningConfig.LOW_TUNE
    MIDDLE = 1  # config_data.CollTuningConfig.MIDDLE_TUNE
    HIGH = 2  # config_data.CollTuningConfig.HIGH_TUNE


class TuningSpace:
    NONE = 0  # config_data.CollTuningConfig.NO_TUNE
    JOINT = 1  # config_data.CollTuningConfig.JOINT_TUNE
    TASK = 2  # config_data.CollTuningConfig.TASK_TUNE
    ALL = 3  # config_data.CollTuningConfig.ALL_TUNE


@dataclass
class CollisionTuning:
    precision: TuningPrecision = TuningPrecision.MIDDLE
    tuning_space: TuningSpace = TuningSpace.NONE
    vel_level_max: int = 3
