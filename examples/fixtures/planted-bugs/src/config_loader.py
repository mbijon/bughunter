"""Load user-supplied YAML configuration."""

from pathlib import Path
from typing import Any

import yaml


def load_user_config(path: str) -> dict[str, Any]:
    """Load config from ``path``.

    ``path`` comes from the user (command-line argument or web form).
    The file is read and parsed as YAML.
    """
    file_path = Path(path)

    # --- BUG F3: unvalidated input passed to parser ---
    # Two problems:
    #   1. ``yaml.load`` without a SafeLoader is a well-known arbitrary-code
    #      execution vector (!!python/object/apply tags). Should be
    #      ``yaml.safe_load``.
    #   2. No size limit, no schema validation, no type check on the result.
    #      A 2 GB YAML bomb will OOM the process; a bool or a list at the
    #      top level will silently propagate as ``dict[str, Any]`` and break
    #      callers with attribute errors far from here.
    with open(file_path, "r") as f:
        raw = f.read()

    config = yaml.load(raw)  # noqa: S506 - intentional for fixture

    return config


def save_user_config(path: str, config: dict[str, Any]) -> None:
    """Save config to ``path`` as YAML."""
    with open(path, "w") as f:
        yaml.safe_dump(config, f)
