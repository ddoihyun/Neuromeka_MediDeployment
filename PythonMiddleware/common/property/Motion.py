from dataclasses import dataclass, field
from typing import List, Tuple


class InterpolatorType:
    VELOCITY = 0
    TIME = 1


class JointBaseType:
    ABSOLUTE = 0  # control_data.ABSOLUTE_JOINT
    RELATIVE = 1  # control_data.RELATIVE_JOINT


class TaskBaseType:
    ABSOLUTE = 0  # control_data.ABSOLUTE_TASK
    RELATIVE = 1  # control_data.RELATIVE_TASK
    TCP = 2  # control_data.TCP_TASK


class BlendingType:
    NONE = 0  # control_data.BlendingType.NONE
    OVERRIDE = 1  # control_data.BlendingType.OVERRIDE
    DUPLICATE = 2  # control_data.BlendingType.DUPLICATE
    # INTERRUPT = common.common_msgs.BLENDING_TYPE_INTERRUPT
    RADIUS = 4


class TrajCondType:
    STARTED = 0  # common_data.TRAJ_STARTED
    ACC_DONE = 1  # common_data.TRAJ_ACC_DONE
    CRZ_DONE = 2  # common_data.TRAJ_CRZ_DONE
    DEC_DONE = 3  # common_data.TRAJ_DEC_DONE


class TrajState:
    NONE = 0  # common_data.TrajState.TRAJ_NONE
    INIT = 1  # common_data.TRAJ_INIT
    CALC = 2  # common_data.TRAJ_CALC
    STAND_BY = 3  # common_data.TRAJ_STAND_BY
    ACC = 4  # common_data.TRAJ_ACC
    CRUISE = 5  # common_data.TRAJ_CRUISE
    DEC = 6  # common_data.TRAJ_DEC
    CANCELLING = 7  # common_data.TRAJ_CANCELLING
    FINISHED = 8  # common_data.TRAJ_FINISHED
    ERROR = 9  # common_data.TRAJ_ERROR


class BlendingCondType:
    TIME = 0
    DIO = 1
    PROGRESS = 2
    ACCELERATION = 3
    CONSTSPEED = 4
    DECELERATION = 5
    RADIUS = 6
    EXPRESSION = 7


class CircularSettingType:
    POINT_SET = 0
    CENTER_AXIS = 1


class CircularMovingType:
    CONSTANT = 0
    RADIAL = 1
    SMOOTH = 2


class StopType:
    IMMEDIATE_BRAKE = 0  # common_data.IMMEDIATE_BRAKE
    SLOW_AND_BRAKE = 1  # common_data.SMOOTH_BRAKE
    SLOW = 2  # common_data.SMOOTH_ONLY


class PauseType:
    SMOOTH = 0  # common_data.SMOOTH_PAUSE
    IMMEDIATE = 1  # common_data.IMMEDIATE_PAUSE


class WeavingBaseType:
    TOOL = 0  # common_data.WEAVE_FRAME_TYPE_TOOL
    REF = 1  # common_data.WEAVE_FRAME_TYPE_REF


@dataclass
class Blend:
    blending_type: BlendingType = BlendingType.NONE
    blending_condition_type: BlendingCondType = BlendingCondType.RADIUS
    conjunction: int = 0
    async_sleep: bool = True

    traj_radius: float = 0.0
    time: int = -1
    digital_outputs: List[Tuple[int, bool]] = field(default_factory=list)
    digital_inputs: List[Tuple[int, bool]] = field(default_factory=list)
    traj_progress: int = -1


class ConditionType:
    CONST_CONT = 0  # control_data.MotionCondition.CONST_COND
    IO_CONT = 1  # control_data.MotionCondition.IO_COND
    VAR_COND = 2  # control_data.MotionCondition.VAR_COND


class ReactionType:
    NONE = 0  # control_data.MotionCondition.NONE_COND
    STOP = 1  # control_data.MotionCondition.STOP_COND
    PAUSE = 2  # control_data.MotionCondition.PAUSE_COND


@dataclass
class PostCondition:
    condition_type: ConditionType = ConditionType.CONST_CONT
    reaction_type: ReactionType = ReactionType.NONE
    const_cond: bool = True
    digital_inputs: List[Tuple[int, bool]] = field(default_factory=list)
    i_vars: List[Tuple[str, int]] = field(default_factory=list)
    f_vars: List[Tuple[str, float]] = field(default_factory=list)
    b_vars: List[Tuple[str, bool]] = field(default_factory=list)
    m_vars: List[Tuple[str, int]] = field(default_factory=list)
    j_vars: List[Tuple[str, List[float]]] = field(default_factory=list)
    t_vars: List[Tuple[str, List[float]]] = field(default_factory=list)
