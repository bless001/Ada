"""
Helper functions for Ada Coding Agent
"""
import os
import json
from typing import Dict, Any

def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    """
    Load configuration from file
    """
    default_config = {
        "debug": False,
        "max_execution_time": 30,
        "supported_languages": ["python"],
        "enable_autonomous_mode": False
    }
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                # Merge with default config
                default_config.update(config)
                return default_config
        except Exception:
            return default_config
    else:
        return default_config

def save_config(config: Dict[str, Any], config_path: str = "config.json") -> bool:
    """
    Save configuration to file
    """
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception:
        return False

def format_code(code: str) -> str:
    """
    Format code (placeholder implementation)
    """
    # In a real implementation, this might use black or autopep8
    return code

def validate_code(code: str) -> bool:
    """
    Validate if code is syntactically correct (placeholder)
    """
    # In a real implementation, this would use AST or other validation methods
    try:
        compile(code, '<string>', 'exec')
        return True
    except SyntaxError:
        return False