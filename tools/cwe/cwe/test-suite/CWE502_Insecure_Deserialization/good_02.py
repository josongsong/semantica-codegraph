"""CWE-502: Insecure Deserialization - GOOD"""

import yaml


def load_config(config_path: str):
    with open(config_path) as f:
        data = f.read()

    # GOOD: yaml.safe_load
    config = yaml.safe_load(data)
    return config
