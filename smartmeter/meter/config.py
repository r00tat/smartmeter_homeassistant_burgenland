"""Fetch addon config"""

import os

import yaml


def get_config_file_name():
    """Get the full path to the config.yaml file."""
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")


def get_config_file_contents():
    """Get the config from config.yaml."""
    with open(get_config_file_name(), encoding="utf-8") as f:
        return f.read()


def get_config() -> dict:
    """Get the config from config.yaml."""
    return yaml.safe_load(get_config_file_contents())


def get_sw_version() -> str:
    """Get the current software version."""
    config = get_config()
    return config.get("version", "")
