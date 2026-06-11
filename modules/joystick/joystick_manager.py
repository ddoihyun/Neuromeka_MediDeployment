import threading
import pygame
import time

from modules.global_data import JoystickCommand
from modules.global_func import get_time
from modules.joystick.joystick_settings import JOYSTICK_INFO_PATH, JoystickSettings
from pkg.utils.blackboard import GlobalBlackboard
from pkg.utils.logging import Logger
from queue import Queue

bb = GlobalBlackboard()

class JoystickManager():
    def __init__(self, *args, **kwargs):
        # 초기화
        self.event_queue = Queue()  # FIFO 큐
        self.event_list = []
        self.connected = {}
        self.dpad_map = {}
        self.thread = None
        self.prev_poll_axis = {}
        self.prev_buttons = {}
        self.prev_hats = {}
        self.axis_map = {}      # axis 번호 → action
        self.prev_axis = {}     # axis 번호 → 이전 값 저장
        self.axis_dir_state = {}  # axis 번호 → 현재 방향 라벨 또는 None
        self.active_model_name = None
        self.supported_names = []
        self.joystick_info = {}
        self.settings = JoystickSettings()

        self.load_model()

        pygame.init()
        pygame.joystick.quit() # 강제 재초기화

        pygame.joystick.init()

        pygame.event.set_blocked(None)
        
        self.last_poll_time = time.time()
        bb.set("joystick/enabled", False)

        self.connected = self.scan_joysticks(initial=True)
        self.update_connection_state()
        self.seed_input_state()
        self.running = False
        self.start()

    def load_model(self, target_model=None):
        if not self.joystick_info:
            self.settings = JoystickSettings.load(JOYSTICK_INFO_PATH)
            self.joystick_info = self.settings.joystick_info
        self._apply_settings()
        controllers = self.settings.controllers()
        if not target_model:
            target_model = self.supported_names[0] if self.supported_names else None
        if not target_model or target_model not in controllers:
            return
        self.active_model_name = target_model
        controller = controllers[target_model]
        buttons = controller["buttons"]
        axes = controller["axes"]
        self.dpad_map = {
            buttons["x2"]: JoystickCommand.ZOOM_OUT, # 8
            buttons["x3"]: JoystickCommand.ZOOM_IN,  # 9 

            buttons["x1"]:JoystickCommand.TILT_W_CW, # 3
            buttons["x4"]:JoystickCommand.TILT_W_CCW, # 3

            buttons["x5"]:JoystickCommand.ENABLE, # 3
            
        }
        self.axis_map = {
            axes["up_down"]: JoystickCommand.TILT_V, # 1
            axes["left_right"]: JoystickCommand.TILT_U, # 0
        }

    def _apply_settings(self):
        self.supported_names = self.settings.supported_names()
        self.joystick_deadzone = self.settings.input_deadzone()
        self.joystick_gain = self.settings.axis_gain()
        self.round_digit = self.settings.round_digit()
        self.poll_interval_sec = self.settings.poll_interval_sec()

    def get_teleop_gain(self, key):
        return self.settings.teleop_gain(key)

    def get_teleop_limit(self, key):
        return self.settings.teleop_limit(key)

    def get_teleop_axis_deadzone(self):
        return self.settings.teleop_axis_deadzone()

    def get_teleop_singularity_slowdown(self):
        return self.settings.teleop_singularity_slowdown()

    def clamp_teleop_delta(self, key, value):
        return self.settings.clamp_teleop_delta(key, value)

    def update_connection_state(self):
        active_js = next(
            (js for js in self.connected.values() if js.get_name() in self.supported_names),
            None,
        )
        if active_js:
            if active_js.get_name() != self.active_model_name:
                self.load_model(active_js.get_name())
            bb.set("joystick/state/connect", True)
        else:
            bb.set("joystick/state/connect", False)

    def scan_joysticks(self, initial=False):
        """현재 연결된 조이스틱 스캔"""
        js_dict = {}
        for i in range(pygame.joystick.get_count()):
            js = pygame.joystick.Joystick(i)
            js.init()
            js_dict[js.get_instance_id()] = js

        if initial:
            if js_dict:
                print(f"초기 연결: {[js.get_name() for js in js_dict.values()]}")
            else:
                print("초기 연결된 조이스틱 없음")

        return js_dict

    def _is_supported_joystick(self, js):
        return not self.supported_names or js.get_name() in self.supported_names

    def _normalize_axis_value(self, value):
        event_value = round(float(value), self.round_digit)
        if abs(event_value) < self.joystick_deadzone:
            event_value = 0.0
        return event_value

    def _clear_input_state(self, instance_id):
        for state in (self.prev_poll_axis, self.prev_buttons, self.prev_hats):
            for key in list(state):
                if key[0] == instance_id:
                    state.pop(key, None)

    def _seed_joystick_state(self, instance_id, js):
        try:
            for button in range(js.get_numbuttons()):
                self.prev_buttons[(instance_id, button)] = bool(js.get_button(button))
            for axis in range(js.get_numaxes()):
                event_value = self._normalize_axis_value(js.get_axis(axis))
                self.prev_poll_axis[(instance_id, axis)] = event_value
                self.prev_axis[axis] = event_value
            for hat in range(js.get_numhats()):
                self.prev_hats[(instance_id, hat)] = tuple(js.get_hat(hat))
        except pygame.error:
            return

    def seed_input_state(self):
        self.prev_poll_axis.clear()
        self.prev_buttons.clear()
        self.prev_hats.clear()
        self.prev_axis.clear()
        self.axis_dir_state.clear()
        try:
            pygame.event.pump()
        except pygame.error:
            return
        for instance_id, js in list(self.connected.items()):
            if self._is_supported_joystick(js):
                self._seed_joystick_state(instance_id, js)

    def poll_inputs(self):
        self.poll_joysticks()
        try:
            pygame.event.pump()
        except pygame.error:
            return

        for instance_id, js in list(self.connected.items()):
            try:
                if not self._is_supported_joystick(js):
                    continue
                if js.get_name() != self.active_model_name:
                    self.load_model(js.get_name())

                for axis in range(js.get_numaxes()):
                    event_value = self._normalize_axis_value(js.get_axis(axis))
                    key = (instance_id, axis)
                    prev_value = self.prev_poll_axis.get(key)
                    self.prev_poll_axis[key] = event_value
                    if prev_value is not None and prev_value != event_value:
                        event = pygame.event.Event(
                            pygame.JOYAXISMOTION,
                            {"axis": axis, "value": event_value},
                        )
                        self.handle_event(event)

                for button in range(js.get_numbuttons()):
                    pressed = bool(js.get_button(button))
                    key = (instance_id, button)
                    prev_value = self.prev_buttons.get(key)
                    self.prev_buttons[key] = pressed
                    if prev_value is not None and prev_value != pressed:
                        event_type = pygame.JOYBUTTONDOWN if pressed else pygame.JOYBUTTONUP
                        event = pygame.event.Event(event_type, {"button": button})
                        self.handle_event(event)

                for hat in range(js.get_numhats()):
                    self.prev_hats[(instance_id, hat)] = tuple(js.get_hat(hat))
            except pygame.error:
                continue


    def poll_joysticks(self):
        if time.time() - self.last_poll_time > self.poll_interval_sec:
            current = self.scan_joysticks()
            # 새로 연결된 조이스틱
            for instance_id, js in current.items():
                if instance_id not in self.connected:
                    self.connected[instance_id] = js
                    if self._is_supported_joystick(js):
                        if js.get_name() != self.active_model_name:
                            self.load_model(js.get_name())
                        self._seed_joystick_state(instance_id, js)
                    Logger.debug(f"{get_time()}: [Joystick] 연결됨 (폴링): {js.get_name()}")
                    
            # 해제된 조이스틱
            for instance_id, js in list(self.connected.items()):
                if instance_id not in current:
                    self.connected.pop(instance_id)
                    self._clear_input_state(instance_id)
                    Logger.debug(f"{get_time()}: [Joystick] 해제됨 (폴링): {js.get_name()}")
            self.update_connection_state()
            self.last_poll_time = time.time()

    def handle_event(self, event):
        action, value = None, None
        """이벤트별 처리 로직"""
        if event.type == pygame.JOYDEVICEADDED:
            js = pygame.joystick.Joystick(event.device_index)
            js.init()
            self.connected[js.get_instance_id()] = js
            action = JoystickCommand.DISCONNECT
            value = None
            Logger.debug(f"{get_time()}: [Joystick] 연결됨 (이벤트): {js.get_name()}")
            self.update_connection_state()

        elif event.type == pygame.JOYDEVICEREMOVED:
            js = self.connected.pop(event.instance_id, None)
            if js:
                action = JoystickCommand.DISCONNECT
                value = None
                Logger.debug(f"{get_time()}: [Joystick] 해제됨 (이벤트): {js.get_name()}")
                self.update_connection_state()

        elif event.type == pygame.JOYAXISMOTION:
            event_axis = event.axis
            action = self.axis_map.get(event_axis)
            if action:
                event_value = self._normalize_axis_value(event.value)

                prev_value = self.prev_axis.get(event_axis, None)
                if prev_value == None: # self.prev_axis[event_axis]
                    prev_value = event_value
                    value = 0
                    action = None

                elif prev_value != event_value:
                    value = event_value * self.joystick_gain
                else:
                    value = 0
                    action = None
                self.prev_axis[event_axis]  = event_value

                # 요청에 따라 "축 입력"/"텔레옵 축 반영"류 로그는 출력하지 않음
                # 대신 방향 발생/해제 로그를 출력
                if action in (JoystickCommand.TILT_U, JoystickCommand.TILT_V):
                    enabled = True if bb.get("joystick/enabled") is True else False
                    status_prefix = "[Enabled]" if enabled else "[Disabled]"
                    # 현재 방향 라벨/사인 계산
                    cur_label = None
                    cur_sign = 0  # +1 or -1
                    if action == JoystickCommand.TILT_V:
                        if value > 0:
                            cur_label, cur_sign = "Z-", +1  # Pitch+
                        elif value < 0:
                            cur_label, cur_sign = "Z+", -1  # Pitch-
                    elif action == JoystickCommand.TILT_U:
                        if value > 0:
                            cur_label, cur_sign = "회전+", +1  # Roll+
                        elif value < 0:
                            cur_label, cur_sign = "회전-", -1  # Roll-
                    prev_label = self.axis_dir_state.get(event_axis)
                    # 발생
                    if cur_label is not None and prev_label != cur_label:
                        if enabled:
                            if action == JoystickCommand.TILT_V:
                                msg = "TCP Pitch+ 회전 시작" if cur_sign > 0 else "TCP Pitch- 회전 시작"
                            else:  # TILT_U
                                msg = "TCP Roll+ 회전 시작" if cur_sign > 0 else "TCP Roll- 회전 시작"
                            Logger.debug(f"{get_time()}: [JOYSTICK] [Enabled] {cur_label} 입력이 발생했습니다.")
                            Logger.debug(f"{get_time()}: [Control] {msg}.")
                        else:
                            Logger.debug(f"{get_time()}: [JOYSTICK] {status_prefix} {cur_label} 입력이 발생했습니다.")
                        self.axis_dir_state[event_axis] = cur_label
                    # 해제
                    if cur_label is None and prev_label is not None:
                        if enabled:
                            # prev_label로 사인 복원
                            if action == JoystickCommand.TILT_V:
                                msg = "TCP Pitch+ 회전 해제" if prev_label == "Z-" else "TCP Pitch- 회전 해제"
                            else:
                                msg = "TCP Roll+ 회전 해제" if prev_label == "회전+" else "TCP Roll- 회전 해제"
                            Logger.debug(f"{get_time()}: [JOYSTICK] [Enabled] {prev_label} 입력이 해제되었습니다.")
                            Logger.debug(f"{get_time()}: [Control] {msg}.")
                        else:
                            Logger.debug(f"{get_time()}: [JOYSTICK] {status_prefix} {prev_label} 입력이 해제되었습니다.")
                        self.axis_dir_state[event_axis] = None

        elif event.type == pygame.JOYBUTTONDOWN:
            # print(event.button)
            action = self.dpad_map.get(event.button)
            if action:
                value = True
                enabled = True if bb.get("joystick/enabled") is True else False
                status_prefix = "[Enabled]" if enabled else "[Disabled]"
                if action == JoystickCommand.ENABLE:
                    bb.set("joystick/enabled", True)
                    Logger.debug(f"{get_time()}: [JOYSTICK] Control Enabled")
                    Logger.debug(f"{get_time()}: [JOYSTICK] [Enabled] 컨트롤러 백 버튼(x5) 입력이 발생했습니다.")
                elif action == JoystickCommand.ZOOM_IN:
                    if enabled:
                        Logger.debug(f"{get_time()}: [JOYSTICK] [Enabled] 컨트롤러 상단 버튼(x2) 입력이 발생했습니다.")
                        Logger.debug(f"{get_time()}: [Control] TCP Z+ 이동 시작.")
                    else:
                        Logger.debug(f"{get_time()}: [JOYSTICK] {status_prefix} 컨트롤러 상단 버튼(x2) 입력이 발생했습니다.")
                elif action == JoystickCommand.ZOOM_OUT:
                    if enabled:
                        Logger.debug(f"{get_time()}: [JOYSTICK] [Enabled] 컨트롤러 하단 버튼(x3) 입력이 발생했습니다.")
                        Logger.debug(f"{get_time()}: [Control] TCP Z- 이동 시작.")
                    else:
                        Logger.debug(f"{get_time()}: [JOYSTICK] {status_prefix} 컨트롤러 하단 버튼(x3) 입력이 발생했습니다.")
                elif action == JoystickCommand.TILT_W_CW:
                    if enabled:
                        Logger.debug(f"{get_time()}: [JOYSTICK] [Enabled] 컨트롤러 좌측 버튼(x1) 입력이 발생했습니다.")
                        Logger.debug(f"{get_time()}: [Control] TCP Yaw- 회전 시작.")
                    else:
                        Logger.debug(f"{get_time()}: [JOYSTICK] {status_prefix} 컨트롤러 좌측 버튼(x1) 입력이 발생했습니다.")
                elif action == JoystickCommand.TILT_W_CCW:
                    if enabled:
                        Logger.debug(f"{get_time()}: [JOYSTICK] [Enabled] 컨트롤러 우측 버튼(x4) 입력이 발생했습니다.")
                        Logger.debug(f"{get_time()}: [Control] TCP Yaw+ 회전 시작.")
                    else:
                        Logger.debug(f"{get_time()}: [JOYSTICK] {status_prefix} 컨트롤러 우측 버튼(x4) 입력이 발생했습니다.")

        elif event.type == pygame.JOYBUTTONUP:
            action = self.dpad_map.get(event.button)
            if action:
                value = False
                enabled = True if bb.get("joystick/enabled") is True else False
                status_prefix = "[Enabled]" if enabled else "[Disabled]"
                if action == JoystickCommand.ENABLE:
                    bb.set("joystick/enabled", False)
                    Logger.debug(f"{get_time()}: [JOYSTICK] Control Disabled")
                    Logger.debug(f"{get_time()}: [JOYSTICK] [Disabled] 컨트롤러 백 버튼(x5) 입력이 해제되었습니다.")
                elif action == JoystickCommand.ZOOM_IN:
                    if enabled:
                        Logger.debug(f"{get_time()}: [JOYSTICK] [Enabled] 컨트롤러 상단 버튼(x2) 입력이 해제되었습니다.")
                        Logger.debug(f"{get_time()}: [Control] TCP Z+ 이동 해제.")
                    else:
                        Logger.debug(f"{get_time()}: [JOYSTICK] {status_prefix} 컨트롤러 상단 버튼(x2) 입력이 해제되었습니다.")
                elif action == JoystickCommand.ZOOM_OUT:
                    if enabled:
                        Logger.debug(f"{get_time()}: [JOYSTICK] [Enabled] 컨트롤러 하단 버튼(x3) 입력이 해제되었습니다.")
                        Logger.debug(f"{get_time()}: [Control] TCP Z- 이동 해제.")
                    else:
                        Logger.debug(f"{get_time()}: [JOYSTICK] {status_prefix} 컨트롤러 하단 버튼(x3) 입력이 해제되었습니다.")
                elif action == JoystickCommand.TILT_W_CW:
                    if enabled:
                        Logger.debug(f"{get_time()}: [JOYSTICK] [Enabled] 컨트롤러 좌측 버튼(x1) 입력이 해제되었습니다.")
                        Logger.debug(f"{get_time()}: [Control] TCP Yaw- 회전 해제.")
                    else:
                        Logger.debug(f"{get_time()}: [JOYSTICK] {status_prefix} 컨트롤러 좌측 버튼(x1) 입력이 해제되었습니다.")
                elif action == JoystickCommand.TILT_W_CCW:
                    if enabled:
                        Logger.debug(f"{get_time()}: [JOYSTICK] [Enabled] 컨트롤러 우측 버튼(x4) 입력이 해제되었습니다.")
                        Logger.debug(f"{get_time()}: [Control] TCP Yaw+ 회전 해제.")
                    else:
                        Logger.debug(f"{get_time()}: [JOYSTICK] {status_prefix} 컨트롤러 우측 버튼(x4) 입력이 해제되었습니다.")

        if action is not None:
            # self.event_queue.put((action, value))
            self.event_list.append((action, value))

            #
            return action,value
        else:
            return None, None

    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()

    def stop(self):
        if self.running:
            self.running = False
            if self.thread:
                self.thread.join()

    def run(self):
        while self.running:
            try:
                self.poll_joysticks()
                time.sleep(0.1)

            except Exception as e:
                self.stop()

    def set_U(self, value):
        bb.set("stick/left_right", value)

    def set_V(self, value):
        bb.set("stick/up_down", value)

    def set_W(self, value):
        bb.set("stick/CCW_CW", value)
        
if __name__ == "__main__":
    manager = JoystickManager()
    manager.start()
    try:
        manager.run()
    except KeyboardInterrupt:
        manager.stop()
