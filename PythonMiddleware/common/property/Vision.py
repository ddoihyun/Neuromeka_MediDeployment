from dataclasses import dataclass, field


class DetectType:
    DETECT = 0
    RETRIEVE = 1


class VisionServerType:
    INDYEYE = 0
    PICKIT = 1
    OMRON = 2


@dataclass
class VisionFrame:
    vision_server: str
    target_object: str


@dataclass
class VisionServer:
    name: str
    vision_server_type: VisionServerType
    ip: str
    port: str


@dataclass
class VisionResult:
    object_name: str
    detected: bool
    passed: bool
    frame: list
