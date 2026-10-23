import base64
import hashlib
import logging
import os
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_ENC_PREFIX = "enc:v1:"


def _is_encrypted_text(value: str) -> bool:
    return value.startswith(_ENC_PREFIX)


def _derive_fernet_key(raw_key: str) -> bytes:
    candidate = raw_key.strip().encode("utf-8")
    try:
        decoded = base64.urlsafe_b64decode(candidate)
        if len(decoded) == 32:
            return candidate
    except Exception:
        pass

    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet | None:
    key = os.getenv("DEERFLOW_SECRETS_ENCRYPTION_KEY", "").strip()
    if not key:
        return None
    return Fernet(_derive_fernet_key(key))


def _fernet_from_raw_key(raw_key: str | None) -> Fernet | None:
    if raw_key is None:
        return None
    key = raw_key.strip()
    if not key:
        return None
    return Fernet(_derive_fernet_key(key))


def reset_crypto_cache() -> None:
    _get_fernet.cache_clear()


def encrypt_text(value: str) -> str:
    if not value or _is_encrypted_text(value):
        return value
    fernet = _get_fernet()
    if fernet is None:
        return value
    token = fernet.encrypt(value.encode("utf-8")).decode("utf-8")
    return f"{_ENC_PREFIX}{token}"


def encrypt_text_with_key(value: str, raw_key: str | None) -> str:
    if not value or _is_encrypted_text(value):
        return value
    fernet = _fernet_from_raw_key(raw_key)
    if fernet is None:
        return value
    token = fernet.encrypt(value.encode("utf-8")).decode("utf-8")
    return f"{_ENC_PREFIX}{token}"


def decrypt_text(value: str) -> str:
    if not value or not _is_encrypted_text(value):
        return value
    fernet = _get_fernet()
    if fernet is None:
        return value

    token = value[len(_ENC_PREFIX) :]
    try:
        return fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        logger.warning("Failed to decrypt secret value: invalid token")
        return value


def decrypt_text_with_key(value: str, raw_key: str | None) -> str:
    if not value or not _is_encrypted_text(value):
        return value
    fernet = _fernet_from_raw_key(raw_key)
    if fernet is None:
        return value
    token = value[len(_ENC_PREFIX) :]
    try:
        return fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return value


def encrypt_text_strict(value: str, raw_key: str | None) -> str:
    """Encrypt all input, including prefix-shaped plaintext; require a key."""
    fernet = _fernet_from_raw_key(raw_key)
    if fernet is None:
        raise ValueError("secret encryption key required")
    return _ENC_PREFIX + fernet.encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_text_strict(value: str, raw_key: str | None) -> str:
    """Reject plaintext and invalid ciphertext instead of returning either."""
    fernet = _fernet_from_raw_key(raw_key)
    if fernet is None:
        raise ValueError("secret encryption key required")
    try:
        if not _is_encrypted_text(value):
            raise ValueError
        return fernet.decrypt(value[len(_ENC_PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError):
        raise ValueError("secret decryption failed") from None


def _map_string_values(value: Any, mapper) -> Any:
    if isinstance(value, dict):
        return {k: _map_string_values(v, mapper) for k, v in value.items()}
    if isinstance(value, list):
        return [_map_string_values(v, mapper) for v in value]
    if isinstance(value, str):
        return mapper(value)
    return value


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    sensitive = {
        "api_key",
        "apikey",
        "secret",
        "client_secret",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "password",
    }
    return lowered in sensitive


def _map_sensitive_fields(value: Any, mapper) -> Any:
    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            if isinstance(v, str) and _is_sensitive_key(str(k)):
                result[k] = mapper(v)
            else:
                result[k] = _map_sensitive_fields(v, mapper)
        return result
    if isinstance(value, list):
        return [_map_sensitive_fields(v, mapper) for v in value]
    return value


def encrypt_model_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return _map_sensitive_fields(settings, encrypt_text)


def decrypt_model_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return _map_sensitive_fields(settings, decrypt_text)


def encrypt_model_settings_with_key(settings: dict[str, Any], raw_key: str | None) -> dict[str, Any]:
    return _map_sensitive_fields(settings, lambda value: encrypt_text_with_key(value, raw_key))


def decrypt_model_settings_with_key(settings: dict[str, Any], raw_key: str | None) -> dict[str, Any]:
    return _map_sensitive_fields(settings, lambda value: decrypt_text_with_key(value, raw_key))


def encrypt_mcp_server_payload(server: dict[str, Any]) -> dict[str, Any]:
    result = dict(server)
    if isinstance(result.get("env"), dict):
        result["env"] = _map_string_values(result["env"], encrypt_text)
    if isinstance(result.get("headers"), dict):
        result["headers"] = _map_string_values(result["headers"], encrypt_text)
    if isinstance(result.get("oauth"), dict):
        result["oauth"] = _map_string_values(result["oauth"], encrypt_text)
    return result


def decrypt_mcp_server_payload(server: dict[str, Any]) -> dict[str, Any]:
    result = dict(server)
    if isinstance(result.get("env"), dict):
        result["env"] = _map_string_values(result["env"], decrypt_text)
    if isinstance(result.get("headers"), dict):
        result["headers"] = _map_string_values(result["headers"], decrypt_text)
    if isinstance(result.get("oauth"), dict):
        result["oauth"] = _map_string_values(result["oauth"], decrypt_text)
    return result


def encrypt_mcp_server_payload_with_key(server: dict[str, Any], raw_key: str | None) -> dict[str, Any]:
    result = dict(server)
    if isinstance(result.get("env"), dict):
        result["env"] = _map_string_values(result["env"], lambda value: encrypt_text_with_key(value, raw_key))
    if isinstance(result.get("headers"), dict):
        result["headers"] = _map_string_values(result["headers"], lambda value: encrypt_text_with_key(value, raw_key))
    if isinstance(result.get("oauth"), dict):
        result["oauth"] = _map_string_values(result["oauth"], lambda value: encrypt_text_with_key(value, raw_key))
    return result


def decrypt_mcp_server_payload_with_key(server: dict[str, Any], raw_key: str | None) -> dict[str, Any]:
    result = dict(server)
    if isinstance(result.get("env"), dict):
        result["env"] = _map_string_values(result["env"], lambda value: decrypt_text_with_key(value, raw_key))
    if isinstance(result.get("headers"), dict):
        result["headers"] = _map_string_values(result["headers"], lambda value: decrypt_text_with_key(value, raw_key))
    if isinstance(result.get("oauth"), dict):
        result["oauth"] = _map_string_values(result["oauth"], lambda value: decrypt_text_with_key(value, raw_key))
    return result


def encrypt_app_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    models = result.get("models")
    if isinstance(models, list):
        result["models"] = [encrypt_model_settings(m) if isinstance(m, dict) else m for m in models]
    return result


def decrypt_app_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    models = result.get("models")
    if isinstance(models, list):
        result["models"] = [decrypt_model_settings(m) if isinstance(m, dict) else m for m in models]
    return result


def encrypt_app_payload_with_key(payload: dict[str, Any], raw_key: str | None) -> dict[str, Any]:
    result = dict(payload)
    models = result.get("models")
    if isinstance(models, list):
        result["models"] = [encrypt_model_settings_with_key(m, raw_key) if isinstance(m, dict) else m for m in models]
    return result


def decrypt_app_payload_with_key(payload: dict[str, Any], raw_key: str | None) -> dict[str, Any]:
    result = dict(payload)
    models = result.get("models")
    if isinstance(models, list):
        result["models"] = [decrypt_model_settings_with_key(m, raw_key) if isinstance(m, dict) else m for m in models]
    return result


def encrypt_extensions_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    servers = result.get("mcpServers")
    if isinstance(servers, dict):
        result["mcpServers"] = {
            name: encrypt_mcp_server_payload(server) if isinstance(server, dict) else server
            for name, server in servers.items()
        }
    return result


def decrypt_extensions_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    servers = result.get("mcpServers")
    if isinstance(servers, dict):
        result["mcpServers"] = {
            name: decrypt_mcp_server_payload(server) if isinstance(server, dict) else server
            for name, server in servers.items()
        }
    return result


def encrypt_extensions_payload_with_key(payload: dict[str, Any], raw_key: str | None) -> dict[str, Any]:
    result = dict(payload)
    servers = result.get("mcpServers")
    if isinstance(servers, dict):
        result["mcpServers"] = {
            name: encrypt_mcp_server_payload_with_key(server, raw_key) if isinstance(server, dict) else server
            for name, server in servers.items()
        }
    return result


def decrypt_extensions_payload_with_key(payload: dict[str, Any], raw_key: str | None) -> dict[str, Any]:
    result = dict(payload)
    servers = result.get("mcpServers")
    if isinstance(servers, dict):
        result["mcpServers"] = {
            name: decrypt_mcp_server_payload_with_key(server, raw_key) if isinstance(server, dict) else server
            for name, server in servers.items()
        }
    return result
