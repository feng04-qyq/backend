"""Runtime configuration loader for trading system.

This module centralises the logic for pulling encrypted configuration
values (Bybit API keys, DeepSeek API key, trading parameters) from the
database and preparing a uniform configuration dict that the trading
managers/engines can consume.

It supports both single-user and multi-user deployments by accepting an
optional ``user_id`` parameter. When no user id is supplied the loader
falls back to shared/global configuration rows (``user_id`` is NULL).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from sqlalchemy.orm import Session

from database_models import Configuration, SessionLocal
from ultra_security import decrypt_api_key


BYBIT_ENVIRONMENTS = ("demo", "testnet", "mainnet")
DEFAULT_BASE_SYMBOLS = ["BTC", "ETH", "SOL"]
DEFAULT_SYMBOLS = [f"{base}USDT" for base in DEFAULT_BASE_SYMBOLS]


def _normalise_symbols_list(symbols: Optional[Iterable[Any]]) -> Optional[list[str]]:
    if symbols is None:
        return None

    tokens: list[str] = []

    def _push(token: str) -> None:
        clean = token.strip().upper()
        if not clean:
            return
        if clean.endswith("_PERPETUAL"):
            clean = clean[:-10]
        if clean.endswith("USDT"):
            clean = clean[:-4]
        clean = "".join(ch for ch in clean if ch.isalnum())
        if not clean:
            return
        if clean not in tokens:
            tokens.append(clean)

    if isinstance(symbols, str):
        splitters = [",", "\n", "\t"]
        text = symbols
        for splitter in splitters:
            text = text.replace(splitter, " ")
        for part in text.split():
            _push(part)
    else:
        for item in symbols:
            if item is None:
                continue
            if isinstance(item, str):
                _push(item)
            elif isinstance(item, dict):
                value = item.get("value")
                if isinstance(value, str):
                    _push(value)

    return tokens or None


def _extract_value(raw_value: Any) -> Any:
    """Normalise ``Configuration.value`` payloads.

    Values are stored in a JSON column. Depending on the history they can be:

    - plain scalar (string / number / bool)
    - object with ``{"value": <actual>, "updated_at": ...}`` if produced by
      the config aggregation helpers
    """

    if isinstance(raw_value, dict) and "value" in raw_value:
        return raw_value.get("value")
    return raw_value


def _decrypt_if_sensitive(value: Any) -> Any:
    if not value or not isinstance(value, str):
        return value

    try:
        return decrypt_api_key(value)
    except Exception:
        # The value might already be plain (legacy data) – fall back silently.
        return value


def _load_category(session: Session, category: str, user_id: Optional[int]) -> Dict[str, Any]:
    query = session.query(Configuration).filter(Configuration.category == category)
    if user_id is not None and hasattr(Configuration, "user_id"):
        query = query.filter(Configuration.user_id == user_id)
    else:
        query = query.filter(Configuration.user_id.is_(None))

    results: Dict[str, Any] = {}
    for row in query.all():
        results[row.key] = _extract_value(row.value)
    return results


def load_trading_runtime_config(
    user_id: Optional[int] = None,
    preferred_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Load decrypted runtime config for the trading engine/manager.

    Returns a dict containing the keys expected by ``LiveTradingEngine`` and
    the trading managers. Raises ``RuntimeError`` if essential credentials are
    missing for the desired environment.
    """

    session = SessionLocal()
    try:
        bybit_entries = _load_category(session, "bybit", user_id)
        deepseek_entries = _load_category(session, "deepseek", user_id)
        trading_entries = _load_category(session, "trading", user_id)
    finally:
        session.close()

    # ------------------------------------------------------------------
    # Bybit credentials
    # ------------------------------------------------------------------
    active_environment = bybit_entries.get("active_environment") or "demo"
    if isinstance(active_environment, dict):  # defensive (legacy data)
        active_environment = active_environment.get("value", "demo")

    if preferred_mode:
        preferred = preferred_mode.lower()
        preferred_map = {
            "demo": "demo",
            "testnet": "testnet",
            "live": "mainnet",
            "mainnet": "mainnet",
        }
        mapped = preferred_map.get(preferred)
        if mapped:
            active_environment = mapped

    if active_environment not in BYBIT_ENVIRONMENTS:
        active_environment = "demo"

    env_credentials: Dict[str, Dict[str, str]] = {}

    for env in BYBIT_ENVIRONMENTS:
        key_raw = bybit_entries.get(f"api_key_{env}")
        secret_raw = bybit_entries.get(f"api_secret_{env}")

        key = _decrypt_if_sensitive(_extract_value(key_raw))
        secret = _decrypt_if_sensitive(_extract_value(secret_raw))

        if key and secret:
            env_credentials[env] = {
                "api_key": key,
                "api_secret": secret,
            }

    # Legacy fallback – single set of keys without env suffix.
    if not env_credentials:
        legacy_key = _decrypt_if_sensitive(_extract_value(bybit_entries.get("api_key")))
        legacy_secret = _decrypt_if_sensitive(_extract_value(bybit_entries.get("api_secret")))
        if legacy_key and legacy_secret:
            env_credentials["demo"] = {
                "api_key": legacy_key,
                "api_secret": legacy_secret,
            }
            if active_environment not in env_credentials:
                active_environment = "demo"

    if active_environment not in env_credentials and env_credentials:
        # Fall back to any environment that has credentials.
        active_environment = next(iter(env_credentials.keys()))

    creds = env_credentials.get(active_environment)
    if not creds:
        raise RuntimeError(
            "No Bybit API credentials found. Please configure API keys for the selected environment."
        )

    use_demo = active_environment == "demo"
    use_testnet = active_environment == "testnet"

    # ------------------------------------------------------------------
    # DeepSeek configuration
    # ------------------------------------------------------------------
    deepseek_api_key = _decrypt_if_sensitive(_extract_value(deepseek_entries.get("api_key")))
    deepseek_model = deepseek_entries.get("model", "deepseek-chat")
    deepseek_system_prompt = deepseek_entries.get("system_prompt")

    # ------------------------------------------------------------------
    # Trading parameters (optional overrides)
    # ------------------------------------------------------------------
    trading_interval = trading_entries.get("interval")
    max_position_pct = trading_entries.get("max_position_pct")
    max_leverage = trading_entries.get("max_leverage")
    enable_trailing = trading_entries.get("enable_trailing_stop")

    runtime_mode = "live" if active_environment == "mainnet" else active_environment

    selected_bases = _normalise_symbols_list(trading_entries.get("symbols"))
    if not selected_bases:
        selected_bases = DEFAULT_BASE_SYMBOLS.copy()

    selected_symbols = [f"{base}USDT" for base in selected_bases]

    config_overrides: Dict[str, Any] = {
        "mode": runtime_mode,
        "active_environment": active_environment,
        "bybit_api_key": creds["api_key"],
        "bybit_api_secret": creds["api_secret"],
        "use_demo": use_demo,
        "use_testnet": use_testnet,
        "symbols": selected_symbols,
    }

    if deepseek_api_key:
        config_overrides["deepseek_api_key"] = deepseek_api_key
    if deepseek_model:
        config_overrides["deepseek_model"] = deepseek_model
    if deepseek_system_prompt:
        config_overrides["deepseek_system_prompt"] = deepseek_system_prompt

    default_base_set = set(DEFAULT_BASE_SYMBOLS)
    selected_base_set = set(selected_bases)

    if selected_base_set != default_base_set:
        prompt = (deepseek_system_prompt or "").strip()
        if not prompt:
            raise RuntimeError(
                "⚠️ 当前已自定义交易对，请先在设置页更新 AI 系统提示词后再启动交易系统。"
            )

    if trading_interval is not None:
        try:
            config_overrides["trading_interval"] = int(trading_interval)
        except (TypeError, ValueError):
            pass

    if max_position_pct is not None:
        try:
            pct = float(max_position_pct)
            # Stored as percentage (0-100), engine expects 0-1.
            config_overrides["max_position_pct"] = pct / 100 if pct > 1 else pct
        except (TypeError, ValueError):
            pass

    if max_leverage is not None:
        try:
            config_overrides["default_leverage"] = int(max_leverage)
        except (TypeError, ValueError):
            pass

    if enable_trailing is not None:
        if isinstance(enable_trailing, bool):
            config_overrides["use_trailing_stop"] = enable_trailing
        else:
            config_overrides["use_trailing_stop"] = str(enable_trailing).lower() == "true"

    return config_overrides


