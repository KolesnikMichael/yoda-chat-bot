from dataclasses import dataclass


@dataclass
class MaintenanceSettings:
    tick_minutes: int

    @classmethod
    def from_dict(cls, block: dict) -> "MaintenanceSettings":
        if "tick_minutes" not in block:
            raise ValueError("Missing required key: tick_minutes")
        return cls(tick_minutes=int(block["tick_minutes"]))
