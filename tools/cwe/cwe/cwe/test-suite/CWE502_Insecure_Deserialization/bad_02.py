"""CWE-502: Insecure Deserialization via YAML - BAD"""

import yaml


def load_config(config_path: str):
    with open(config_path) as f:
        data = f.read()  # SOURCE: file input

    # BAD: yaml.load without safe_load
    config = yaml.load(data)  # SINK: code execution
    return config
