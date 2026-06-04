"""
统一配置加载器
消除 llm.py / agent.py / game_engine.py / ui/app.py 中 4 处重复的 load_config()
支持 ${ENV_VAR} 环境变量替换
"""
import os
import re
import yaml

_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_CONFIG_DIR, "config.yaml")
_config_cache = None


def _resolve_env_vars(value):
    """递归解析字符串中的 ${ENV_VAR} 占位符"""
    if isinstance(value, str):
        pattern = re.compile(r'\$\{(\w+)\}')
        def replacer(match):
            env_key = match.group(1)
            return os.environ.get(env_key, match.group(0))
        return pattern.sub(replacer, value)
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(v) for v in value]
    return value


def load_config(force_reload=False):
    """加载 config.yaml，支持 ${ENV_VAR} 环境变量替换
    
    Args:
        force_reload: 是否强制重新加载（忽略缓存）
    
    Returns:
        dict: 解析后的配置字典
    """
    global _config_cache
    if _config_cache is not None and not force_reload:
        return _config_cache

    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    _config_cache = _resolve_env_vars(raw)
    return _config_cache


def get_config():
    """获取缓存的配置（不会重新读文件）"""
    global _config_cache
    if _config_cache is None:
        return load_config()
    return _config_cache


def reload_config():
    """强制重新加载配置"""
    return load_config(force_reload=True)