from modules.constants import *
from .strategy import *

class SystemFsmSequence(FiniteStateMachine):
    context: SystemContext

    def __init__(self, context: SystemContext, *args, **kwargs):
        FiniteStateMachine.__init__(self, SystemFsmState.NOT_READY, context, *args, **kwargs)

    def _setup_rules(self):
        self._rule_table = {
            SystemFsmState.ERROR: {
                SystemFsmEvent.RECOVER: SystemFsmState.RECOVER,
                SystemFsmEvent.NOT_READY: SystemFsmState.NOT_READY,
            },

            SystemFsmState.RECOVER: {
                SystemFsmEvent.ERROR: SystemFsmState.ERROR,
                SystemFsmEvent.IDLE: SystemFsmState.IDLE,
                SystemFsmEvent.NOT_READY: SystemFsmState.NOT_READY
            },

            SystemFsmState.NOT_READY: {
                SystemFsmEvent.ERROR: SystemFsmState.ERROR,
                SystemFsmEvent.PREP: SystemFsmState.PREP,
            },

            SystemFsmState.PREP: {
                SystemFsmEvent.ERROR: SystemFsmState.ERROR,
                SystemFsmEvent.MANUAL_CONTROL: SystemFsmState.MANUAL_CONTROL,
                SystemFsmEvent.DIRECT_TEACHING: SystemFsmState.DIRECT_TEACHING,
                SystemFsmEvent.FIXED_POINT_CONTROL: SystemFsmState.FIXED_POINT_CONTROL,
                SystemFsmEvent.FIXED_LINE_CONTROL: SystemFsmState.FIXED_LINE_CONTROL,
                SystemFsmEvent.FIXED_PLANE_CONTROL: SystemFsmState.FIXED_PLANE_CONTROL,
                SystemFsmEvent.IDLE: SystemFsmState.IDLE,
                SystemFsmEvent.DEBUG_MOTION: SystemFsmState.DEBUG_MOTION,
                
            },

            SystemFsmState.IDLE: {
                SystemFsmEvent.ERROR: SystemFsmState.ERROR,
                SystemFsmEvent.NOT_READY: SystemFsmState.NOT_READY,
                SystemFsmEvent.VOICE_CONTROL: SystemFsmState.VOICE_CONTROL,
                SystemFsmEvent.VOICE_DIRECT_TEACHING: SystemFsmState.VOICE_DIRECT_TEACHING,
                SystemFsmEvent.VOICE_FIXED_POINT_CONTROL: SystemFsmState.VOICE_FIXED_POINT_CONTROL,
                SystemFsmEvent.VOICE_FIXED_LINE_CONTROL: SystemFsmState.VOICE_FIXED_LINE_CONTROL,
                SystemFsmEvent.VOICE_FIXED_PLANE_CONTROL: SystemFsmState.VOICE_FIXED_PLANE_CONTROL,
                SystemFsmEvent.JOYSTICK_CONTROL: SystemFsmState.JOYSTICK_CONTROL,
                SystemFsmEvent.BUTTON_CONTROL: SystemFsmState.BUTTON_CONTROL,
                SystemFsmEvent.UPDATE_GAIN: SystemFsmState.UPDATE_GAIN,
                SystemFsmEvent.MANUAL_CONTROL: SystemFsmState.MANUAL_CONTROL,
                SystemFsmEvent.DIRECT_TEACHING: SystemFsmState.DIRECT_TEACHING,
                SystemFsmEvent.FIXED_POINT_CONTROL: SystemFsmState.FIXED_POINT_CONTROL,
                SystemFsmEvent.FIXED_LINE_CONTROL: SystemFsmState.FIXED_LINE_CONTROL,
                SystemFsmEvent.FIXED_PLANE_CONTROL: SystemFsmState.FIXED_PLANE_CONTROL,
                SystemFsmEvent.DEBUG_MOTION: SystemFsmState.DEBUG_MOTION,
            },
            SystemFsmState.DIRECT_TEACHING: {
                SystemFsmEvent.ERROR: SystemFsmState.ERROR,
                SystemFsmEvent.NOT_READY: SystemFsmState.NOT_READY,
                SystemFsmEvent.IDLE: SystemFsmState.IDLE,
                SystemFsmEvent.PREP: SystemFsmState.PREP,
            },
            SystemFsmState.MANUAL_CONTROL: {
                SystemFsmEvent.ERROR: SystemFsmState.ERROR,
                SystemFsmEvent.NOT_READY: SystemFsmState.NOT_READY,
                SystemFsmEvent.IDLE: SystemFsmState.IDLE,
                SystemFsmEvent.PREP: SystemFsmState.PREP,
            },

            SystemFsmState.JOYSTICK_CONTROL: {
                SystemFsmEvent.ERROR: SystemFsmState.ERROR,
                SystemFsmEvent.NOT_READY: SystemFsmState.NOT_READY,
                SystemFsmEvent.IDLE: SystemFsmState.IDLE,
            },

            SystemFsmState.FIXED_POINT_CONTROL: {
                SystemFsmEvent.ERROR: SystemFsmState.ERROR,
                SystemFsmEvent.NOT_READY: SystemFsmState.NOT_READY,
                SystemFsmEvent.IDLE: SystemFsmState.IDLE,
                SystemFsmEvent.PREP: SystemFsmState.PREP,
            },
            SystemFsmState.FIXED_LINE_CONTROL: {
                SystemFsmEvent.ERROR: SystemFsmState.ERROR,
                SystemFsmEvent.NOT_READY: SystemFsmState.NOT_READY,
                SystemFsmEvent.IDLE: SystemFsmState.IDLE,
                SystemFsmEvent.PREP: SystemFsmState.PREP,
            },
            SystemFsmState.FIXED_PLANE_CONTROL: {
                SystemFsmEvent.ERROR: SystemFsmState.ERROR,
                SystemFsmEvent.NOT_READY: SystemFsmState.NOT_READY,
                SystemFsmEvent.IDLE: SystemFsmState.IDLE,
                SystemFsmEvent.PREP: SystemFsmState.PREP,
            },
            SystemFsmState.VOICE_CONTROL: {
                SystemFsmEvent.ERROR: SystemFsmState.ERROR,
                SystemFsmEvent.NOT_READY: SystemFsmState.NOT_READY,
                SystemFsmEvent.IDLE: SystemFsmState.IDLE,
                SystemFsmEvent.VOICE_DIRECT_TEACHING: SystemFsmState.VOICE_DIRECT_TEACHING,
                SystemFsmEvent.VOICE_FIXED_POINT_CONTROL: SystemFsmState.VOICE_FIXED_POINT_CONTROL,
                SystemFsmEvent.VOICE_FIXED_LINE_CONTROL: SystemFsmState.VOICE_FIXED_LINE_CONTROL,
                SystemFsmEvent.VOICE_FIXED_PLANE_CONTROL: SystemFsmState.VOICE_FIXED_PLANE_CONTROL,
            },
            SystemFsmState.VOICE_DIRECT_TEACHING: {
                SystemFsmEvent.ERROR: SystemFsmState.ERROR,
                SystemFsmEvent.NOT_READY: SystemFsmState.NOT_READY,
                SystemFsmEvent.IDLE: SystemFsmState.IDLE,
                SystemFsmEvent.VOICE_FIXED_POINT_CONTROL: SystemFsmState.VOICE_FIXED_POINT_CONTROL,
                SystemFsmEvent.VOICE_FIXED_LINE_CONTROL: SystemFsmState.VOICE_FIXED_LINE_CONTROL,
                SystemFsmEvent.VOICE_FIXED_PLANE_CONTROL: SystemFsmState.VOICE_FIXED_PLANE_CONTROL,
            },
            SystemFsmState.VOICE_FIXED_POINT_CONTROL: {
                SystemFsmEvent.ERROR: SystemFsmState.ERROR,
                SystemFsmEvent.NOT_READY: SystemFsmState.NOT_READY,
                SystemFsmEvent.IDLE: SystemFsmState.IDLE,
                SystemFsmEvent.VOICE_DIRECT_TEACHING: SystemFsmState.VOICE_DIRECT_TEACHING,
                SystemFsmEvent.VOICE_FIXED_LINE_CONTROL: SystemFsmState.VOICE_FIXED_LINE_CONTROL,
                SystemFsmEvent.VOICE_FIXED_PLANE_CONTROL: SystemFsmState.VOICE_FIXED_PLANE_CONTROL,
            },
            SystemFsmState.VOICE_FIXED_LINE_CONTROL: {
                SystemFsmEvent.ERROR: SystemFsmState.ERROR,
                SystemFsmEvent.NOT_READY: SystemFsmState.NOT_READY,
                SystemFsmEvent.IDLE: SystemFsmState.IDLE,
                SystemFsmEvent.VOICE_DIRECT_TEACHING: SystemFsmState.VOICE_DIRECT_TEACHING,
                SystemFsmEvent.VOICE_FIXED_POINT_CONTROL: SystemFsmState.VOICE_FIXED_POINT_CONTROL,
                SystemFsmEvent.VOICE_FIXED_PLANE_CONTROL: SystemFsmState.VOICE_FIXED_PLANE_CONTROL,
            },
            SystemFsmState.VOICE_FIXED_PLANE_CONTROL: {
                SystemFsmEvent.ERROR: SystemFsmState.ERROR,
                SystemFsmEvent.NOT_READY: SystemFsmState.NOT_READY,
                SystemFsmEvent.IDLE: SystemFsmState.IDLE,
                SystemFsmEvent.VOICE_DIRECT_TEACHING: SystemFsmState.VOICE_DIRECT_TEACHING,
                SystemFsmEvent.VOICE_FIXED_POINT_CONTROL: SystemFsmState.VOICE_FIXED_POINT_CONTROL,
                SystemFsmEvent.VOICE_FIXED_LINE_CONTROL: SystemFsmState.VOICE_FIXED_LINE_CONTROL,
            },
            SystemFsmState.BUTTON_CONTROL: {
                SystemFsmEvent.ERROR: SystemFsmState.ERROR,
                SystemFsmEvent.NOT_READY: SystemFsmState.NOT_READY,
                SystemFsmEvent.IDLE: SystemFsmState.IDLE,
            },

            SystemFsmState.UPDATE_GAIN: {
                SystemFsmEvent.ERROR: SystemFsmState.ERROR,
                SystemFsmEvent.NOT_READY: SystemFsmState.NOT_READY,
                SystemFsmEvent.IDLE: SystemFsmState.IDLE,
            },
            SystemFsmState.DEBUG_MOTION: {
                SystemFsmEvent.ERROR: SystemFsmState.ERROR,
                SystemFsmEvent.NOT_READY: SystemFsmState.NOT_READY,
            },

        }

    def _setup_strategies(self):
        self._strategy_table = {
            SystemFsmState.NOT_READY: not_ready_strategy(),
            SystemFsmState.PREP: prep_strategy(),            
            SystemFsmState.IDLE:idle_strategy(),
            SystemFsmState.ERROR: error_strategy(),
            SystemFsmState.RECOVER: recover_strategy(),
            SystemFsmState.VOICE_CONTROL: voice_control_strategy(),
            SystemFsmState.VOICE_DIRECT_TEACHING: voice_direct_teaching_strategy(),
            SystemFsmState.VOICE_FIXED_POINT_CONTROL: voice_fixed_point_strategy(),
            SystemFsmState.VOICE_FIXED_LINE_CONTROL: voice_fixed_line_strategy(),
            SystemFsmState.VOICE_FIXED_PLANE_CONTROL: voice_fixed_plane_strategy(),
            SystemFsmState.JOYSTICK_CONTROL: joystick_control_strategy(),
            SystemFsmState.BUTTON_CONTROL: button_control_strategy(),
            SystemFsmState.UPDATE_GAIN: update_gain_strategy(),
            SystemFsmState.MANUAL_CONTROL: manual_control_strategy(),
            SystemFsmState.DIRECT_TEACHING: direct_teaching_strategy(),
            SystemFsmState.DEBUG_MOTION: debug_motion_strategy(),
            SystemFsmState.FIXED_POINT_CONTROL: fixed_point_strategy(),
            SystemFsmState.FIXED_LINE_CONTROL: fixed_line_strategy(),
            SystemFsmState.FIXED_PLANE_CONTROL: fixed_plane_strategy()

        }

