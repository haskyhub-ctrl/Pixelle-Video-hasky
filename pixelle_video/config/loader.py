# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Configuration loader - Pure YAML

Handles loading and saving configuration from/to YAML files.
"""
import os
from pathlib import Path

import yaml
from loguru import logger


def _load_dotenv(path: str = ".env") -> None:
    """Load KEY=VALUE lines from a .env file into os.environ (no overwrite)."""
    env_file = Path(path)
    if not env_file.exists():
        return
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception as e:
        logger.warning(f"Failed to read {path}: {e}")


# Environment variable -> nested config path. Lets users run locally with a
# .env file instead of editing config.yaml, and keeps secrets out of the repo.
_ENV_MAP = {
    "LLM_API_KEY": ("llm", "api_key"),
    "LLM_BASE_URL": ("llm", "base_url"),
    "LLM_MODEL": ("llm", "model"),
    "YOUTUBE_API_KEY": ("niche", "youtube_api_key"),
    "TIKHUB_API_KEY": ("niche", "tikhub_api_key"),
    "NICHE_DEFAULT_REGION": ("niche", "default_region"),
    "NICHE_DEFAULT_LANGUAGE": ("niche", "default_language"),
}


def apply_env_overrides(data: dict) -> dict:
    """Overlay environment variables (and .env) onto a config dict."""
    _load_dotenv()
    for env_key, (section, field) in _ENV_MAP.items():
        value = os.environ.get(env_key)
        if value:
            data.setdefault(section, {})
            if isinstance(data[section], dict):
                data[section][field] = value
    return data


def load_config_dict(config_path: str = "config.yaml") -> dict:
    """
    Load configuration from YAML file
    
    Args:
        config_path: Path to config file
        
    Returns:
        Configuration dictionary
    """
    config_file = Path(config_path)
    
    if not config_file.exists():
        logger.warning(f"Config file not found: {config_path}")
        logger.info("Using default configuration")
        return {}
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        logger.info(f"Configuration loaded from {config_path}")
        return data
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return {}


def save_config_dict(config: dict, config_path: str = "config.yaml"):
    """
    Save configuration to YAML file
    
    Args:
        config: Configuration dictionary
        config_path: Path to config file
    """
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        logger.info(f"Configuration saved to {config_path}")
    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        raise

