"""
config/loader.py —— .claw.yaml 配置加载
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class ClawConfig:
    model: str = "deepseek-chat"
    work_dir: str = "."
    enable_thinking: bool = False
    plan_mode: bool = False

    compactor_max_chars: int = 20000
    compactor_retain_last: int = 6

    tools: dict[str, bool] = field(default_factory=lambda: {
        "read_file": True,
        "write_file": True,
        "bash": True,
        "edit_file": True,
    })


def load_config(path: Optional[str] = None) -> ClawConfig:
    """从 .claw.yaml 加载配置，没文件就用默认值"""
    config = ClawConfig()
    file_path = Path(path) if path else Path(".claw.yaml")
    if not file_path.exists():
        return config

    with open(file_path) as f:
        data = yaml.safe_load(f) or {}

    if "model" in data:
        config.model = data["model"]
    if "enable_thinking" in data:
        config.enable_thinking = data["enable_thinking"]
    if "plan_mode" in data:
        config.plan_mode = data["plan_mode"]
    if "compactor" in data:
        c = data["compactor"]
        if "max_chars" in c:
            config.compactor_max_chars = c["max_chars"]
        if "retain_last" in c:
            config.compactor_retain_last = c["retain_last"]

    return config
