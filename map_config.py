"""Local-only AMap credentials. Never print values or include them in errors."""
import json
import os
from pathlib import Path
import re
import tempfile

CONFIG_PATH = Path(__file__).resolve().parent / 'data' / 'amap.local.json'


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError('配置格式不正确。请重新运行配置工具。')
    result = {}
    for name in ('js_key', 'security_code'):
        value = config.get(name)
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', value):
            raise ValueError('Key 或安全密钥格式不正确，请复制完整值，不要包含名称或空格。')
        result[name] = value
    if result['js_key'] == result['security_code']:
        raise ValueError('两项内容相同。请分别复制 Key 和安全密钥。')
    web_key = config.get('web_key', '')
    if web_key:
        if not isinstance(web_key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', web_key):
            raise ValueError('Web 服务 Key 格式不正确。')
        if web_key in result.values():
            raise ValueError('Web 服务 Key 需要与网页地图 Key 和安全密钥不同。')
        result['web_key'] = web_key
    return result


def load_config(path=CONFIG_PATH):
    if not path.exists():
        return None
    try:
        return validate_config(json.loads(path.read_text(encoding='utf-8')))
    except (ValueError, OSError):
        raise ValueError('地图配置无法读取，请重新运行配置工具。') from None


def save_config(config, path=CONFIG_PATH):
    values = validate_config(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=str(path.parent),
                                         prefix='amap-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(values, stream)
        os.replace(str(temporary), str(path))
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
