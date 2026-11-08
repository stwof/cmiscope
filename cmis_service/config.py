"""Configuration loader: built-in defaults -> config.ini -> environment vars.

Precedence increases from left to right. Every path is resolved relative to
BASE_DIR, so the whole directory can be copied to another host without code
changes. Secrets are never stored in config.ini: the REST token is read from an
environment variable named by rest_token_env, and SSH uses the operator's
existing ssh-agent keys with BatchMode=yes.
"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_CANDIDATES = ("config.ini", "config.ini.example")

_BOOL_TRUE = {"1", "true", "yes", "on"}
_BOOL_FALSE = {"0", "false", "no", "off"}
_ACCESS_MODES = ("mirror", "ssh-i2c", "rest-api")

# ini section/key -> Settings field name
_INI_MAP = {
    ("server", "host"): "host",
    ("server", "port"): "port",
    ("paths", "data_dir"): "data_dir",
    ("paths", "static_dir"): "static_dir",
    ("paths", "db_file"): "db_file",
    ("paths", "seed_file"): "seed_file",
    ("paths", "kg_file"): "kg_file",
    ("app", "read_only"): "read_only",
    ("app", "write_adapter"): "write_adapter",
    ("app", "access_mode"): "access_mode",
    ("app", "default_language"): "default_language",
    ("app", "operator"): "operator",
    ("ssh", "host"): "ssh_host",
    ("ssh", "user"): "ssh_user",
    ("ssh", "port"): "ssh_port",
    ("ssh", "timeout_seconds"): "ssh_timeout",
    ("ssh", "i2c_bus"): "i2c_bus",
    ("ssh", "i2c_addr"): "i2c_addr",
    ("ssh", "probe_cmd"): "ssh_probe_cmd",
    ("ssh", "read_cmd"): "ssh_read_cmd",
    ("ssh", "write_cmd"): "ssh_write_cmd",
    ("ssh", "cdb_cmd"): "ssh_cdb_cmd",
    ("rest", "base_url"): "rest_base_url",
    ("rest", "token_env"): "rest_token_env",
    ("rest", "timeout_seconds"): "rest_timeout",
    ("rest", "probe_path"): "rest_probe_path",
    ("rest", "read_path"): "rest_read_path",
    ("rest", "write_path"): "rest_write_path",
    ("rest", "cdb_path"): "rest_cdb_path",
    ("security", "allow_hardware_write"): "allow_hardware_write",
    ("security", "cdb_allow_firmware"): "cdb_allow_firmware",
    ("security", "cdb_rest_allowed"): "cdb_rest_allowed",
    ("security", "cdb_confirm_token"): "cdb_confirm_token",
    ("limits", "max_body_bytes"): "max_body_bytes",
    ("limits", "log_level"): "log_level",
}

# environment variable -> Settings field name
_ENV_MAP = {
    "CMIS_HOST": "host",
    "CMIS_PORT": "port",
    "CMIS_BASE_DIR": "base_dir",
    "CMIS_DATA_DIR": "data_dir",
    "CMIS_STATIC_DIR": "static_dir",
    "CMIS_DB_FILE": "db_file",
    "CMIS_SEED_FILE": "seed_file",
    "CMIS_KG_FILE": "kg_file",
    "CMIS_READ_ONLY": "read_only",
    "CMIS_WRITE_ADAPTER": "write_adapter",
    "CMIS_ACCESS_MODE": "access_mode",
    "CMIS_DEFAULT_LANGUAGE": "default_language",
    "CMIS_OPERATOR": "operator",
    "CMIS_SSH_HOST": "ssh_host",
    "CMIS_SSH_USER": "ssh_user",
    "CMIS_SSH_PORT": "ssh_port",
    "CMIS_SSH_TIMEOUT": "ssh_timeout",
    "CMIS_I2C_BUS": "i2c_bus",
    "CMIS_I2C_ADDR": "i2c_addr",
    "CMIS_SSH_PROBE_CMD": "ssh_probe_cmd",
    "CMIS_SSH_READ_CMD": "ssh_read_cmd",
    "CMIS_SSH_WRITE_CMD": "ssh_write_cmd",
    "CMIS_SSH_CDB_CMD": "ssh_cdb_cmd",
    "CMIS_REST_BASE_URL": "rest_base_url",
    "CMIS_REST_TOKEN_ENV": "rest_token_env",
    "CMIS_REST_TIMEOUT": "rest_timeout",
    "CMIS_REST_PROBE_PATH": "rest_probe_path",
    "CMIS_REST_READ_PATH": "rest_read_path",
    "CMIS_REST_WRITE_PATH": "rest_write_path",
    "CMIS_REST_CDB_PATH": "rest_cdb_path",
    "CMIS_ALLOW_HARDWARE_WRITE": "allow_hardware_write",
    "CMIS_CDB_ALLOW_FIRMWARE": "cdb_allow_firmware",
    "CMIS_CDB_REST_ALLOWED": "cdb_rest_allowed",
    "CMIS_CDB_CONFIRM_TOKEN": "cdb_confirm_token",
    "CMIS_MAX_BODY_BYTES": "max_body_bytes",
    "CMIS_LOG_LEVEL": "log_level",
}

_PATH_FIELDS = {"base_dir", "data_dir", "static_dir", "db_file", "seed_file", "kg_file"}
_INT_FIELDS = {"port", "max_body_bytes", "ssh_port", "ssh_timeout", "rest_timeout"}
_BOOL_FIELDS = {"read_only", "allow_hardware_write", "cdb_allow_firmware", "cdb_rest_allowed"}


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8787
    base_dir: Path = BASE_DIR
    data_dir: Path = BASE_DIR / "data"
    static_dir: Path = BASE_DIR / "cmis_service" / "static"
    db_file: Path = BASE_DIR / "data" / "cmis.db"
    seed_file: Path = BASE_DIR / "data" / "seed.json"
    kg_file: Path = BASE_DIR / "data" / "knowledge_graph.json"
    read_only: bool = False
    # write_adapter is kept for backward compatibility and mirrors access_mode
    write_adapter: str = "mirror"
    access_mode: str = "mirror"
    default_language: str = "zh"
    operator: str = "local-admin"
    log_level: str = "INFO"
    max_body_bytes: int = 65536

    # Mode A: SSH to a test switch, then I2C to the module EEPROM
    ssh_host: str = ""
    ssh_user: str = "admin"
    ssh_port: int = 22
    ssh_timeout: int = 8
    i2c_bus: str = "0"
    i2c_addr: str = "0x50"
    ssh_probe_cmd: str = "ssh -p {port} -o BatchMode=yes -o ConnectTimeout={timeout} {user}@{host} echo CMIS-PROBE-OK"
    ssh_read_cmd: str = ("ssh -p {port} -o BatchMode=yes -o ConnectTimeout={timeout} {user}@{host} "
                         "i2cdump -y {bus} {addr} b")
    ssh_write_cmd: str = ("ssh -p {port} -o BatchMode=yes -o ConnectTimeout={timeout} {user}@{host} "
                          "i2cset -y {bus} {addr} {offset} {value}")
    ssh_cdb_cmd: str = ""

    # Mode B: northbound RESTful API of the target device / NOS
    rest_base_url: str = ""
    rest_token_env: str = "CMIS_REST_TOKEN"
    rest_timeout: int = 8
    rest_probe_path: str = "/api/cmis/health"
    rest_read_path: str = "/api/cmis/registers"
    rest_write_path: str = "/api/cmis/registers"
    rest_cdb_path: str = "/api/cmis/cdb"

    # Safety gates, all disabled by default
    allow_hardware_write: bool = False
    cdb_allow_firmware: bool = False
    cdb_rest_allowed: bool = False
    cdb_confirm_token: str = "EXECUTE"


def _as_bool(value: str) -> bool:
    v = str(value).strip().lower()
    if v in _BOOL_TRUE:
        return True
    if v in _BOOL_FALSE:
        return False
    raise ValueError(f"Cannot parse boolean value {value!r} (use true/false/1/0)")


def _resolve(base: Path, raw: str) -> Path:
    p = Path(os.path.expandvars(str(raw))).expanduser()
    return p if p.is_absolute() else (base / p)


def load_settings(config_path: str | os.PathLike | None = None, environ=None) -> Settings:
    """Load settings. Without config_path, check CMIS_CONFIG, config.ini, then example."""
    env = dict(os.environ if environ is None else environ)
    base = _resolve(BASE_DIR, env.get("CMIS_BASE_DIR", str(BASE_DIR)))

    path = config_path or env.get("CMIS_CONFIG")
    if path is None:
        for name in DEFAULT_CONFIG_CANDIDATES:
            candidate = base / name
            if candidate.is_file():
                path = candidate
                break
    cfg_path = Path(path) if path else None
    if cfg_path is not None and not cfg_path.is_absolute():
        cfg_path = base / cfg_path

    values: dict = {}
    if cfg_path and cfg_path.is_file():
        parser = configparser.ConfigParser()
        with cfg_path.open("r", encoding="utf-8") as fh:
            parser.read_file(fh)
        for (section, key), field in _INI_MAP.items():
            if parser.has_option(section, key):
                values[field] = parser.get(section, key).strip()

    for env_key, field in _ENV_MAP.items():
        if env_key in env and str(env[env_key]).strip() != "":
            values[field] = env[env_key]

    # The final base_dir value anchors every other relative path
    if "base_dir" in values:
        base = _resolve(BASE_DIR, values.pop("base_dir"))

    parsed: dict = {"base_dir": base}
    for field, raw in values.items():
        if field in _PATH_FIELDS:
            parsed[field] = _resolve(base, raw)
        elif field in _INT_FIELDS:
            parsed[field] = int(raw)
        elif field in _BOOL_FIELDS:
            parsed[field] = _as_bool(raw)
        else:
            parsed[field] = str(raw)

    settings = Settings(**parsed)
    # Backward compatibility: either key can select the transport
    if settings.access_mode == "mirror" and settings.write_adapter in _ACCESS_MODES:
        settings = type(settings)(**{**settings.__dict__, "access_mode": settings.write_adapter})
    if not 1 <= settings.port <= 65535:
        raise ValueError(f"Port out of range: {settings.port}")
    if settings.max_body_bytes < 1024:
        raise ValueError("max_body_bytes must be at least 1024")
    if settings.access_mode not in _ACCESS_MODES:
        raise ValueError(f"access_mode must be one of {', '.join(_ACCESS_MODES)}")
    if settings.default_language not in ("zh", "en"):
        raise ValueError("default_language must be 'zh' or 'en'")
    return settings


def public_settings(settings: Settings) -> dict:
    """Return a safe configuration summary for the browser (no secrets)."""
    return {
        "host": settings.host,
        "port": settings.port,
        "base_dir": str(settings.base_dir),
        "data_dir": str(settings.data_dir),
        "db_file": str(settings.db_file),
        "seed_file": str(settings.seed_file),
        "kg_file": str(settings.kg_file),
        "read_only": settings.read_only,
        "access_mode": settings.access_mode,
        "default_language": settings.default_language,
        "operator": settings.operator,
        "log_level": settings.log_level,
        "allow_hardware_write": settings.allow_hardware_write,
        "cdb_allow_firmware": settings.cdb_allow_firmware,
        "cdb_rest_allowed": settings.cdb_rest_allowed,
        "ssh": {"host": settings.ssh_host, "user": settings.ssh_user,
                "port": settings.ssh_port, "i2c_bus": settings.i2c_bus,
                "i2c_addr": settings.i2c_addr},
        "rest": {"base_url": settings.rest_base_url, "token_env": settings.rest_token_env,
                 "token_present": bool(os.environ.get(settings.rest_token_env))},
    }
