"""
Insecure Deserialization Fixtures

CVE-2019-20477: Python pickle RCE
CVE-2017-17485: YAML unsafe load RCE
CVE-2013-7285: Django pickle session vulnerability
"""

import json
import pickle

import yaml

# ==================================================
# VULNERABLE: pickle.loads() with user input (RCE!)
# ==================================================


def load_user_session_vulnerable(session_data: bytes) -> dict:
    """
    ❌ CRITICAL: Deserializing user-controlled pickle data

    CVE-2019-20477: pickle.loads() allows arbitrary code execution!

    Attack example:
        import pickle, os
        class Evil:
            def __reduce__(self):
                return (os.system, ('rm -rf /',))
        pickle.dumps(Evil())  # Will execute command on loads()
    """
    return pickle.loads(session_data)


def load_cached_data_vulnerable(cache_key: str, user_input: bytes) -> object:
    """
    ❌ CRITICAL: Loading pickle from untrusted source

    Even if not directly from user, pickle should never
    deserialize untrusted data.
    """
    obj = pickle.load(open("/tmp/cache", "rb"))
    return obj


def load_config_pickle_vulnerable(config_path: str) -> dict:
    """
    ❌ CRITICAL: Loading config as pickle

    If attacker can modify config file, they can execute code.
    """
    with open(config_path, "rb") as f:
        config = pickle.load(f)
    return config


# ==================================================
# VULNERABLE: YAML unsafe load (RCE!)
# ==================================================


def load_yaml_config_vulnerable(yaml_content: str) -> dict:
    """
    ❌ CRITICAL: Using yaml.load() without safe loader

    CVE-2017-17485: yaml.load() can execute arbitrary Python code.

    Attack example:
        !!python/object/apply:os.system ['rm -rf /']
    """
    return yaml.load(yaml_content)


def load_yaml_from_user_vulnerable(user_yaml: str) -> dict:
    """
    ❌ CRITICAL: Loading user-provided YAML unsafely
    """
    return yaml.unsafe_load(user_yaml)


# ==================================================
# SECURE: JSON for data, safe_load for YAML
# ==================================================


def load_user_session_secure(session_data_json: str) -> dict:
    """
    ✅ SECURE: Using JSON for session data

    JSON only supports basic data types, no code execution.
    """
    return json.loads(session_data_json)


def load_config_json_secure(config_path: str) -> dict:
    """
    ✅ SECURE: Using JSON for config files
    """
    with open(config_path) as f:
        config = json.load(f)
    return config


def load_yaml_config_secure(yaml_content: str) -> dict:
    """
    ✅ SECURE: Using yaml.safe_load()

    safe_load() only constructs simple Python objects.
    """
    return yaml.safe_load(yaml_content)


def load_yaml_from_user_secure(user_yaml: str) -> dict:
    """
    ✅ SECURE: Safe YAML loading with validation
    """
    data = yaml.safe_load(user_yaml)

    # Additional validation
    if not isinstance(data, dict):
        raise ValueError("Expected dict")

    return data


# ==================================================
# Context: When pickle is acceptable
# ==================================================


def save_ml_model_internal(model: object, path: str):
    """
    ✅ ACCEPTABLE: Pickle for trusted internal data

    Pickle is OK for:
    - Internal caching (not user-accessible)
    - ML model serialization (trusted source)
    - IPC between trusted processes

    But NEVER for user input or untrusted sources!
    """
    with open(path, "wb") as f:
        pickle.dump(model, f)
