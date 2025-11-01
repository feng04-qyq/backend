"""
配置管理 API（Config Manager）
============================

用途：为前端提供集中式配置入口，用于管理 DeepSeek、Bybit 以及交易参数等敏感设置。
特点：
  • 集成多用户权限控制，按需返回配置
  • 支持前端加密通道与后端 7 层加密存储
  • 验证第三方 API（Bybit/DeepSeek），并将结果标准化输出
  • 保存成功后自动刷新运行时环境变量，便于其它模块即时读取
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List, Union, Tuple
from types import SimpleNamespace
from enum import Enum
import os
import json
from datetime import datetime
import hashlib
import base64
import hmac
import time
from urllib.parse import urlencode
import requests
import logging

# 配置日志（必须在导入检查之前）
logger = logging.getLogger(__name__)

# 数据库
from database_models import get_db, Configuration
from sqlalchemy.orm import Session
from fastapi import Request

# 导入认证依赖
try:
    from api_auth import get_current_user, get_current_user_optional
except ImportError:
    # 如果无法导入，创建一个占位符
    def get_current_user_optional():
        return None

router = APIRouter(prefix="/api/config", tags=["配置管理"])

# 获取当前用户（用于配置管理）
async def get_current_user_for_config(
    user = Depends(get_current_user_optional)
):
    """获取当前用户对象，如果没有则返回 None"""
    return user

# 获取当前用户或访客（返回用户名字符串）- 保留兼容性
async def get_current_user_or_guest(
    user = Depends(get_current_user_optional)
):
    """获取当前用户，如果没有则返回 'guest'"""
    if user:
        return user.username
    return "guest"

# ============================================================================
# 超安全加密工具
# ============================================================================

# 导入超安全加密系统
from ultra_security import encrypt_api_key, decrypt_api_key
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

class ConfigEncryption:
    """
    配置加密工具 - 使用军事级7层加密
    
    加密层级：
    1. 密钥派生函数 (PBKDF2) - 100,000次迭代
    2. AES-256-GCM加密
    3. RSA-4096加密
    4. Fernet双重加密
    5. 自定义混淆算法
    6. Base85编码
    7. HMAC完整性校验
    """
    
    def encrypt(self, text: str) -> str:
        """7层加密"""
        try:
            return encrypt_api_key(text)
        except Exception as e:
            logging.error(f"加密失败: {e}")
            raise
    
    def decrypt(self, encrypted_text: str) -> str:
        """7层解密"""
        try:
            return decrypt_api_key(encrypted_text)
        except Exception as e:
            logging.error(f"解密失败: {e}")
            raise

crypto = ConfigEncryption()

SENSITIVE_KEYWORDS = ("key", "secret", "token", "pass", "password")

# ==========================================================================
# 客户端加密传输处理工具
# ==========================================================================

def _b64decode_field(value: str, field_name: str) -> bytes:
    try:
        return base64.b64decode(value)
    except Exception as exc:  # pragma: no cover - 防御性异常
        raise ValueError(f"无效的Base64编码字段: {field_name}") from exc


def _derive_aes_key_from_token(token: str, salt: bytes) -> bytes:
    if not token:
        raise ValueError("缺少授权令牌，无法完成加密通信")
    return hashlib.pbkdf2_hmac(
        "sha256",
        token.encode("utf-8"),
        salt,
        120_000,
        dklen=32,
    )


def decrypt_client_payload(envelope: Dict[str, Any], auth_token: str) -> Dict[str, Any]:
    if not isinstance(envelope, dict):
        raise ValueError("加密数据格式不正确")

    required_fields = {"iv", "data", "tag", "salt"}
    missing_fields = required_fields - set(envelope.keys())
    if missing_fields:
        raise ValueError(f"加密数据缺少字段: {', '.join(sorted(missing_fields))}")

    iv = _b64decode_field(envelope["iv"], "iv")
    ciphertext = _b64decode_field(envelope["data"], "data")
    tag = _b64decode_field(envelope["tag"], "tag")
    salt = _b64decode_field(envelope["salt"], "salt")

    aes_key = _derive_aes_key_from_token(auth_token, salt)

    cipher = Cipher(
        algorithms.AES(aes_key),
        modes.GCM(iv, tag),
        backend=default_backend(),
    )
    decryptor = cipher.decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    decoded = plaintext.decode("utf-8")
    try:
        return json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise ValueError("解密后的数据不是有效的JSON") from exc


def extract_config_payload(data: Dict[str, Any], request: Request) -> Dict[str, Any]:
    if isinstance(data, dict) and data.get("encrypted"):
        payload = data.get("payload")
        if payload is None:
            raise HTTPException(status_code=400, detail="加密数据缺少payload字段")

        auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
        if not auth_header or not auth_header.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="缺少身份验证令牌，无法解析加密数据")

        auth_token = auth_header.split(" ", 1)[1].strip()
        try:
            return decrypt_client_payload(payload, auth_token)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"加密数据解析失败: {exc}")
    return data

# ============================================================================
# Pydantic模型
# ============================================================================

class DeepSeekConfig(BaseModel):
    """DeepSeek配置"""
    api_key: str = Field(..., description="DeepSeek API密钥")
    base_url: str = Field(default="https://api.deepseek.com", description="API基础URL")
    model: str = Field(default="deepseek-chat", description="模型名称")
    temperature: float = Field(default=0.7, ge=0, le=2, description="温度参数")
    max_tokens: int = Field(default=4000, ge=100, le=8000, description="最大token数")
    system_prompt: Optional[str] = Field(default=None, description="自定义系统提示词", max_length=20000)
    
    @validator('api_key')
    def validate_api_key(cls, v):
        if not v or len(v) < 10:
            raise ValueError("API密钥格式不正确")
        return v

class BybitEnvironment(str, Enum):
    demo = "demo"
    testnet = "testnet"
    mainnet = "mainnet"


class BybitCredential(BaseModel):
    api_key: Optional[str] = Field(default=None, description="Bybit API密钥")
    api_secret: Optional[str] = Field(default=None, description="Bybit API密钥")

    @validator('api_key', 'api_secret', pre=True, always=True)
    def allow_empty_or_valid(cls, v):
        if v is None or v == "":
            return None
        if len(v) < 10:
            raise ValueError("API密钥格式不正确")
        return v


class BybitValidationRequest(BaseModel):
    """Bybit验证请求"""
    api_key: str = Field(..., description="Bybit API密钥")
    api_secret: str = Field(..., description="Bybit API密钥")
    environment: BybitEnvironment = Field(default=BybitEnvironment.demo, description="目标环境")
    
    @validator('api_key', 'api_secret')
    def validate_keys(cls, v):
        if not v or len(v) < 10:
            raise ValueError("API密钥格式不正确")
        return v


class BybitMultiConfig(BaseModel):
    """Bybit多环境配置"""
    demo: BybitCredential = Field(default_factory=BybitCredential)
    testnet: BybitCredential = Field(default_factory=BybitCredential)
    mainnet: BybitCredential = Field(default_factory=BybitCredential)
    active_environment: BybitEnvironment = Field(default=BybitEnvironment.demo, description="当前默认环境")


BYBIT_ENVIRONMENTS: Tuple[BybitEnvironment, ...] = (
    BybitEnvironment.demo,
    BybitEnvironment.testnet,
    BybitEnvironment.mainnet,
)

class TradingParams(BaseModel):
    """交易参数"""
    trading_interval: int = Field(default=180, ge=60, le=3600, description="交易间隔（秒）")
    max_position_pct: float = Field(default=30, ge=5, le=50, description="最大仓位百分比")
    min_position_pct: float = Field(default=3, ge=1, le=20, description="最小仓位百分比")
    max_leverage: int = Field(default=15, ge=1, le=20, description="最大杠杆")
    stop_loss_pct: float = Field(default=2, ge=0.5, le=10, description="止损百分比")
    take_profit_pct: float = Field(default=5, ge=1, le=20, description="止盈百分比")
    use_trailing_stop: bool = Field(default=True, description="是否启用移动止损")
    trailing_stop_distance_atr: float = Field(default=2.0, ge=1, le=5, description="移动止损距离（ATR倍数）")
    trailing_stop_trigger_atr: float = Field(default=3.0, ge=1, le=5, description="移动止损触发（ATR倍数）")

class RiskParams(BaseModel):
    """风险参数"""
    max_daily_loss: float = Field(default=500, ge=100, le=10000, description="最大日亏损（美元）")
    max_drawdown_pct: float = Field(default=10, ge=5, le=30, description="最大回撤百分比")
    enable_drawdown_analysis: bool = Field(default=True, description="启用回撤分析")
    auto_trading: bool = Field(default=True, description="自动交易")

class SystemConfig(BaseModel):
    """完整系统配置"""
    deepseek: Optional[DeepSeekConfig] = None
    bybit: Optional[BybitMultiConfig] = None
    trading: Optional[TradingParams] = None
    risk: Optional[RiskParams] = None

class ConfigUpdateRequest(BaseModel):
    """配置更新请求"""
    category: str = Field(..., description="配置类别: deepseek/bybit/trading/risk")
    config: Dict[str, Any] = Field(..., description="配置内容")
    validate_before_save: bool = Field(default=True, description="保存前验证")

class ConfigValidationResponse(BaseModel):
    """配置验证响应"""
    valid: bool
    message: str
    details: Optional[Dict[str, Any]] = None

# ============================================================================
# 配置验证器
# ============================================================================

class ConfigValidator:
    """配置验证器"""
    
    @staticmethod
    async def validate_deepseek(config: DeepSeekConfig) -> ConfigValidationResponse:
        """验证DeepSeek配置"""
        try:
            # 测试API调用
            headers = {
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": config.model,
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 10,
                "temperature": config.temperature
            }
            
            response = requests.post(
                f"{config.base_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=10
            )
            
            if response.status_code == 200:
                return ConfigValidationResponse(
                    valid=True,
                    message="✅ DeepSeek API验证成功",
                    details={
                        "model": config.model,
                        "base_url": config.base_url,
                        "response_time": response.elapsed.total_seconds()
                    }
                )
            else:
                return ConfigValidationResponse(
                    valid=False,
                    message=f"❌ API验证失败: {response.status_code}",
                    details={"error": response.text}
                )
                
        except Exception as e:
            return ConfigValidationResponse(
                valid=False,
                message=f"❌ 验证过程出错: {str(e)}",
                details={"error": str(e)}
            )
    
    @staticmethod
    async def validate_bybit(config: BybitValidationRequest) -> ConfigValidationResponse:
        """调用 Bybit v5 接口校验密钥有效性，并提供友好提示。"""

        try:
            # 1. 选择环境与候选域名
            environment = config.environment
            if environment == BybitEnvironment.demo:
                environment_label = "模拟盘"
                candidate_endpoints = ["https://api-demo.bybit.com"]
            elif environment == BybitEnvironment.testnet:
                environment_label = "测试网"
                candidate_endpoints = ["https://api-testnet.bybit.com"]
            else:
                environment_label = "实盘"
                candidate_endpoints = [
                    "https://api.bybit.com",
                    "https://api.bytick.com",  # 官方备用域名
                ]

            query_params = {"accountType": "UNIFIED"}
            query_string = urlencode(query_params)
            last_error: Optional[Exception] = None

            # 2. 遍历候选域名并尝试验证
            for base_url in candidate_endpoints:
                try:
                    timestamp = str(int(time.time() * 1000))
                    recv_window = "5000"
                    sign_payload = f"{timestamp}{config.api_key}{recv_window}{query_string}"
                    signature = hmac.new(
                        config.api_secret.encode("utf-8"),
                        sign_payload.encode("utf-8"),
                        hashlib.sha256,
                    ).hexdigest()

                    headers = {
                        "X-BAPI-API-KEY": config.api_key,
                        "X-BAPI-SIGN": signature,
                        "X-BAPI-SIGN-TYPE": "2",
                        "X-BAPI-TIMESTAMP": timestamp,
                        "X-BAPI-RECV-WINDOW": recv_window,
                        "Content-Type": "application/json",
                    }

                    url = f"{base_url}/v5/account/wallet-balance?{query_string}"
                    response = requests.get(url, headers=headers, timeout=10)
                    response.raise_for_status()
                    data = response.json()

                    ret_code = data.get("retCode")
                    ret_msg = data.get("retMsg", "") or ""

                    # 速率限制：视为验证通过，但提示用户稍后重试
                    if ret_code == 10006 or "rate limit" in ret_msg.lower():
                            return ConfigValidationResponse(
                            valid=True,
                            message="⚠️ API密钥格式正确，但遇到速率限制。请稍后再试。",
                                details={
                                "environment": environment_label,
                                "error_code": ret_code,
                                "error_msg": ret_msg,
                                "endpoint": base_url,
                                "suggestion": "请等待几分钟后重试或降低请求频率",
                            },
                            )
                    
                    if ret_code == 0:
                        # 校验成功，解析 USDT 余额（若存在）
                        balance = 0.0
                        try:
                            result_list = data.get("result", {}).get("list", [])
                            if result_list:
                                coins = result_list[0].get("coin", [])
                                usdt_coin = next((c for c in coins if c.get("coin") == "USDT"), None)
                                if usdt_coin:
                                    balance = float(usdt_coin.get("walletBalance", 0))
                        except Exception:
                            balance = 0.0

                        return ConfigValidationResponse(
                            valid=True,
                            message="✅ Bybit API验证成功",
                            details={
                                "environment": environment_label,
                                "balance": f"${balance:,.2f}",
                                "account_type": "UNIFIED",
                                "endpoint": base_url,
                            },
                        )

                    if ret_code == 10003:
                        return ConfigValidationResponse(
                            valid=False,
                            message="❌ API验证失败: API key is invalid. (ErrCode: 10003)",
                            details={
                                "error_code": ret_code,
                                "error_msg": ret_msg,
                                "environment": environment_label,
                                "endpoint": base_url,
                                "suggestion": "请确认所选环境与密钥一致，并检查密钥是否启用了Unified账户权限",
                            },
                        )

                    # 其它错误：返回详细提示，帮助定位问题
                    return ConfigValidationResponse(
                        valid=False,
                        message=f"❌ API验证失败: {ret_msg or '未知错误'}",
                        details={
                            "error_code": ret_code,
                            "error_msg": ret_msg,
                            "environment": environment_label,
                            "endpoint": base_url,
                            "suggestion": "请检查API密钥是否正确以及权限设置是否完整",
                        },
                    )

                except (requests.Timeout, requests.ConnectionError) as conn_error:
                    # 记录最后一次连接错误，循环尝试其它域名
                    last_error = conn_error
                    continue
                except requests.RequestException as req_error:
                    # 非连接类错误直接返回，避免误导用户
                    return ConfigValidationResponse(
                        valid=False,
                        message=f"❌ 验证过程出错: {req_error}",
                        details={
                            "error": str(req_error),
                            "environment": environment_label,
                            "endpoint": base_url,
                        },
                    )

            # 若所有候选域名都尝试失败，按最后一次连接错误返回
            if last_error is not None:
                raise last_error

            return ConfigValidationResponse(
                valid=False,
                message="❌ 无法连接到任何 Bybit 端点，请检查网络或稍后再试",
                details={
                    "environment": environment_label,
                    "endpoints": candidate_endpoints,
                },
            )

        except requests.Timeout:
            return ConfigValidationResponse(
                valid=False,
                message="❌ API验证超时，请检查网络或稍后再试",
                details={"error": "timeout"},
            )
        except Exception as exc:
            return ConfigValidationResponse(
                valid=False,
                message=f"❌ 验证过程出错: {exc}",
                details={"error": str(exc)},
            )

validator = ConfigValidator()

# ============================================================================
# API端点
# ============================================================================

@router.get("")
@router.get("/all")
async def get_all_config(
    current_user_obj = Depends(get_current_user_for_config),
    db: Session = Depends(get_db)
):
    """
    获取当前用户的所有配置（敏感信息脱敏）
    
    v3.3 多用户架构：每个用户只能看到自己的配置
    """
    try:
        # v3.3: 按用户查询配置
        if current_user_obj:
            # 已登录用户：查询自己的配置
            configs = db.query(Configuration).filter(
                Configuration.user_id == current_user_obj.id
            ).all()
        else:
            # 未登录用户：返回空配置
            configs = []
        
        result = {
            "deepseek": {},
            "bybit": {},
            "trading": {},
            "risk": {}
        }
        
        for config in configs:
            category = config.category
            key = config.key
            value = config.value
            
            # 脱敏处理
            if category in ["deepseek", "bybit"] and any(keyword in key.lower() for keyword in SENSITIVE_KEYWORDS):
                # 只显示前4位和后4位
                if isinstance(value, str) and len(value) > 8:
                    value = f"{value[:4]}...{value[-4:]}"
            
            if category not in result:
                result[category] = {}
            
            result[category][key] = {
                "value": value,
                "description": config.description,
                "updated_at": config.updated_at.isoformat() if config.updated_at else None
            }
        
        if result.get("bybit") is not None:
            result["bybit"] = _compose_bybit_masked(result.get("bybit", {}))
        
        return {
            "success": True,
            "data": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{category}")
async def get_config_by_category(
    category: str,
    current_user_obj = Depends(get_current_user_for_config),
    db: Session = Depends(get_db)
):
    """
    获取指定类别的配置
    
    v3.3 多用户架构：返回当前用户在该类别下的配置
    """
    try:
        # v3.3: 按用户和类别查询
        query = db.query(Configuration).filter(
            Configuration.category == category
        )
        
        if current_user_obj:
            # 已登录用户：只查询自己的配置
            query = query.filter(Configuration.user_id == current_user_obj.id)
        else:
            # 未登录用户：返回空
            return {
                "success": True,
                "category": category,
                "data": {}
            }
        
        configs = query.all()
        
        result = {}
        for config in configs:
            value = config.value
            
            # 脱敏处理
            if category in ["deepseek", "bybit"] and any(keyword in config.key.lower() for keyword in SENSITIVE_KEYWORDS):
                if isinstance(value, str) and len(value) > 8:
                    value = f"{value[:4]}...{value[-4:]}"
            
            result[config.key] = {
                "value": value,
                "description": config.description,
                "updated_at": config.updated_at.isoformat() if config.updated_at else None
            }
        
        data_payload: Union[Dict[str, Any], Dict[str, Dict[str, Any]]] = result
        if category == "bybit":
            data_payload = _compose_bybit_masked(result)
        
        return {
            "success": True,
            "category": category,
            "data": data_payload
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/validate/deepseek")
async def validate_deepseek_config(request: Request, config_payload: Dict[str, Any]):
    """验证DeepSeek配置"""
    config_dict = extract_config_payload(config_payload, request)
    config = DeepSeekConfig(**config_dict)
    result = await validator.validate_deepseek(config)
    return result

@router.post("/validate/bybit")
async def validate_bybit_config(request: Request, config_payload: Dict[str, Any]):
    """验证Bybit配置"""
    config_dict = extract_config_payload(config_payload, request)
    config = BybitValidationRequest(**config_dict)
    result = await validator.validate_bybit(config)
    return result

@router.put("/{category}")
async def update_config_category(
    category: str,
    config_data: Dict[str, Any],
    request: Request,
    current_user_obj = Depends(get_current_user_for_config),
    db: Session = Depends(get_db)
):
    """
    更新指定类别的配置（兼容前端调用方式）
    
    v3.3 多用户架构：每个用户保存自己的配置
    """
    # 要求用户必须登录
    if not current_user_obj or not current_user_obj.id:
        raise HTTPException(
            status_code=401,
            detail="需要登录才能更新配置"
        )
    
    try:
        processed_config = extract_config_payload(config_data, request)

        if category == "bybit":
            return await handle_bybit_update(processed_config, current_user_obj, db)

        if category == "deepseek" and "api_key" in processed_config:
            validation = await validator.validate_deepseek(DeepSeekConfig(**processed_config))
            if not validation.valid:
                raise HTTPException(status_code=400, detail=validation.message)
        
        # 保存配置到数据库
        updated_keys = []
        for key, value in processed_config.items():
            # v3.3: 按用户查询配置
            config_entry = db.query(Configuration).filter(
                Configuration.category == category,
                Configuration.key == key,
                Configuration.user_id == current_user_obj.id  # 只查询当前用户的配置
            ).first()
            
            # 敏感信息加密
            if category in ["deepseek", "bybit"] and any(keyword in key.lower() for keyword in SENSITIVE_KEYWORDS):
                value = crypto.encrypt(str(value))
            
            if config_entry:
                # 更新现有配置
                config_entry.value = value
                config_entry.updated_at = datetime.utcnow()
            else:
                # 创建新配置（关联到当前用户）
                config_entry = Configuration(
                    user_id=current_user_obj.id,  # v3.3: 关联到当前用户
                    category=category,
                    key=key,
                    value=value,
                    description=f"{category}.{key}"
                )
                db.add(config_entry)
            
            updated_keys.append(key)
        
        db.commit()
        
        # 更新环境变量
        if category == "deepseek":
            if "api_key" in processed_config:
                os.environ["DEEPSEEK_API_KEY"] = processed_config["api_key"]
            if "base_url" in processed_config:
                os.environ["DEEPSEEK_BASE_URL"] = processed_config["base_url"]
            if "system_prompt" in processed_config:
                os.environ["DEEPSEEK_SYSTEM_PROMPT"] = processed_config["system_prompt"]
        
        return {
            "success": True,
            "message": f"配置已更新: {', '.join(updated_keys)}",
            "category": category,
            "updated_keys": updated_keys
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


def _upsert_config_value(
    db: Session,
    user_id: int,
    category: str,
    key: str,
    value: Any,
    encrypt: bool = False,
) -> str:
    config_entry = db.query(Configuration).filter(
        Configuration.category == category,
        Configuration.key == key,
        Configuration.user_id == user_id,
    ).first()

    stored_value: Any = value
    if encrypt and value is not None:
        stored_value = crypto.encrypt(str(value))

    if config_entry:
        config_entry.value = stored_value
        config_entry.updated_at = datetime.utcnow()
    else:
        config_entry = Configuration(
            user_id=user_id,
            category=category,
            key=key,
            value=stored_value,
            description=f"{category}.{key}"
        )
        db.add(config_entry)

    return key


async def handle_bybit_update(
    processed_config: Dict[str, Any],
    current_user_obj,
    db: Session,
) -> Dict[str, Any]:
    if not isinstance(processed_config, dict):
        raise HTTPException(status_code=400, detail="请求数据格式不正确")

    user_id = current_user_obj.id

    credentials_container = processed_config.get("credentials")
    env_payloads = credentials_container if isinstance(credentials_container, dict) else processed_config

    credentials_to_save: Dict[str, Dict[str, str]] = {}
    updated_keys: List[str] = []

    for env in BYBIT_ENVIRONMENTS:
        env_name = env.value
        env_payload = env_payloads.get(env_name)
        if env_payload is None:
            continue

        if not isinstance(env_payload, dict):
            raise HTTPException(status_code=400, detail=f"{env_name} 配置格式不正确")

        api_key = env_payload.get("api_key")
        api_secret = env_payload.get("api_secret")

        if api_key is None and api_secret is None:
            continue

        if bool(api_key) ^ bool(api_secret):
            raise HTTPException(status_code=400, detail=f"{env_name} 环境请同时提供 API Key 和 Secret")

        if api_key is not None and api_secret is not None:
            validation = await validator.validate_bybit(
                BybitValidationRequest(
                    api_key=api_key,
                    api_secret=api_secret,
                    environment=env,
                )
            )
            if not validation.valid:
                raise HTTPException(status_code=400, detail=validation.message)

            credentials_to_save[env_name] = {
                "api_key": api_key,
                "api_secret": api_secret,
            }

    active_environment_value = processed_config.get("active_environment")
    active_environment: Optional[BybitEnvironment] = None
    if active_environment_value is not None:
        try:
            active_environment = BybitEnvironment(active_environment_value)
        except ValueError:
            raise HTTPException(status_code=400, detail="active_environment 无效，应为 demo/testnet/mainnet")

    try:
        if active_environment is not None:
            updated_keys.append(
                _upsert_config_value(
                    db,
                    user_id,
                    category="bybit",
                    key="active_environment",
                    value=active_environment.value,
                    encrypt=False,
                )
            )

        for env_name, creds in credentials_to_save.items():
            for field, raw_value in creds.items():
                store_key = f"{field}_{env_name}"
                updated_keys.append(
                    _upsert_config_value(
                        db,
                        user_id,
                        category="bybit",
                        key=store_key,
                        value=raw_value,
                        encrypt=True,
                    )
                )

        db.commit()
    except Exception:
        db.rollback()
        raise

    if active_environment is not None:
        os.environ["BYBIT_ACTIVE_ENVIRONMENT"] = active_environment.value

    for env_name, creds in credentials_to_save.items():
        uppercase = env_name.upper()
        os.environ[f"BYBIT_API_KEY_{uppercase}"] = creds["api_key"]
        os.environ[f"BYBIT_API_SECRET_{uppercase}"] = creds["api_secret"]

    message = "配置已更新" if updated_keys else "没有检测到需要更新的内容"

    return {
        "success": True,
        "message": message,
        "category": "bybit",
        "updated_keys": updated_keys,
    }


def _compose_bybit_masked(entries: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    if not entries:
        return {"active_environment": "demo", "environments": {}}

    active_env = entries.get("active_environment", {}).get("value", "demo")
    environments: Dict[str, Dict[str, Optional[str]]] = {}

    for env in BYBIT_ENVIRONMENTS:
        env_name = env.value
        env_data: Dict[str, Optional[str]] = {}
        key_entry = entries.get(f"api_key_{env_name}")
        if isinstance(key_entry, dict):
            env_data["api_key"] = key_entry.get("value")
        secret_entry = entries.get(f"api_secret_{env_name}")
        if isinstance(secret_entry, dict):
            env_data["api_secret"] = secret_entry.get("value")
        if env_data:
            environments[env_name] = env_data

    legacy_key = entries.get("api_key")
    legacy_secret = entries.get("api_secret")
    if legacy_key or legacy_secret:
        legacy_env = environments.setdefault("demo", {})
        if isinstance(legacy_key, dict):
            legacy_env.setdefault("api_key", legacy_key.get("value"))
        if isinstance(legacy_secret, dict):
            legacy_env.setdefault("api_secret", legacy_secret.get("value"))

    return {
        "active_environment": active_env,
        "environments": environments,
    }


def _compose_bybit_plain(entries: Dict[str, Any]) -> Dict[str, Any]:
    if not entries:
        return {"active_environment": "demo", "environments": {}}

    active_env = entries.get("active_environment", "demo")
    environments: Dict[str, Dict[str, Optional[str]]] = {}

    for env in BYBIT_ENVIRONMENTS:
        env_name = env.value
        env_data: Dict[str, Optional[str]] = {}
        key_value = entries.get(f"api_key_{env_name}")
        if key_value:
            env_data["api_key"] = key_value
        secret_value = entries.get(f"api_secret_{env_name}")
        if secret_value:
            env_data["api_secret"] = secret_value
        if env_data:
            environments[env_name] = env_data

    legacy_key = entries.get("api_key")
    legacy_secret = entries.get("api_secret")
    if legacy_key or legacy_secret:
        legacy_env = environments.setdefault("demo", {})
        if legacy_key:
            legacy_env.setdefault("api_key", legacy_key)
        if legacy_secret:
            legacy_env.setdefault("api_secret", legacy_secret)

    return {
        "active_environment": active_env,
        "environments": environments,
    }


# 内部函数：实际执行配置更新的逻辑
async def _update_config_internal(
    category: str,
    config: Dict[str, Any],
    user_id: int,
    validate_before_save: bool,
    db: Session
) -> dict:
    """
    内部函数：执行配置更新
    
    Args:
        category: 配置类别
        config: 配置字典
        user_id: 用户ID
        validate_before_save: 是否在保存前验证
        db: 数据库会话
    
    Returns:
        更新结果字典
    """
    if category == "bybit":
        dummy_user = SimpleNamespace(id=user_id)
        return await handle_bybit_update(config, dummy_user, db)

    # 验证配置
    if validate_before_save and category == "deepseek":
            validation = await validator.validate_deepseek(
                DeepSeekConfig(**config)
            )
            if not validation.valid:
                raise HTTPException(
                    status_code=400,
                    detail=validation.message
                )
    
    # 保存配置到数据库（按用户）
    updated_keys = []
    for key, value in config.items():
        # v3.3: 按用户查询配置
        config_entry = db.query(Configuration).filter(
            Configuration.category == category,
            Configuration.key == key,
            Configuration.user_id == user_id  # 只查询当前用户的配置
        ).first()
        
        # 敏感信息加密
        if category in ["deepseek", "bybit"] and any(keyword in key.lower() for keyword in SENSITIVE_KEYWORDS):
            value = crypto.encrypt(str(value))
        
        if config_entry:
            # 更新
            config_entry.value = value
            config_entry.updated_at = datetime.utcnow()
        else:
            # 创建（关联到当前用户）
            config_entry = Configuration(
                user_id=user_id,  # v3.3: 关联到当前用户
                category=category,
                key=key,
                value=value,
                description=f"{category}.{key}"
            )
            db.add(config_entry)
        
        updated_keys.append(key)
    
    db.commit()
    
    if category == "deepseek":
        if "api_key" in config:
            os.environ["DEEPSEEK_API_KEY"] = str(config["api_key"])
        if "base_url" in config:
            os.environ["DEEPSEEK_BASE_URL"] = str(config["base_url"])
        if "system_prompt" in config:
            os.environ["DEEPSEEK_SYSTEM_PROMPT"] = str(config["system_prompt"])
    elif category == "bybit":
        if "api_key" in config:
            os.environ["BYBIT_API_KEY"] = str(config["api_key"])
        if "api_secret" in config:
            os.environ["BYBIT_API_SECRET"] = str(config["api_secret"])
        if "use_demo" in config:
            os.environ["USE_DEMO"] = str(config["use_demo"]).lower()
        if "use_testnet" in config:
            os.environ["USE_TESTNET"] = str(config["use_testnet"]).lower()
    
    return {
        "success": True,
        "message": f"✅ 配置已更新: {', '.join(updated_keys)}",
        "category": category,
        "updated_keys": updated_keys
    }

@router.put("/update")
async def update_config(
    http_request: Request,
    request: ConfigUpdateRequest,
    current_user_obj = Depends(get_current_user_for_config),
    db: Session = Depends(get_db)
):
    """
    更新配置（按用户区分）
    
    v3.3 多用户架构：每个用户保存自己的配置
    """
    # 要求用户必须登录
    if not current_user_obj or not current_user_obj.id:
        raise HTTPException(
            status_code=401,
            detail="需要登录才能更新配置"
        )
    
    try:
        processed_config = extract_config_payload(request.config, http_request)
        return await _update_config_internal(
            category=request.category,
            config=processed_config,
            user_id=current_user_obj.id,
            validate_before_save=request.validate_before_save,
            db=db
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/batch_update")
async def batch_update_config(
    config: SystemConfig,
    current_user_obj = Depends(get_current_user_for_config),
    db: Session = Depends(get_db)
):
    """
    批量更新配置（按用户区分）
    
    v3.3 多用户架构：每个用户保存自己的配置
    """
    # 要求用户必须登录
    if not current_user_obj or not current_user_obj.id:
        raise HTTPException(
            status_code=401,
            detail="需要登录才能更新配置"
        )
    
    try:
        results = []
        
        # DeepSeek配置
        if config.deepseek:
            result = await _update_config_internal(
                category="deepseek",
                config=config.deepseek.dict(),
                user_id=current_user_obj.id,
                validate_before_save=True,
                db=db
            )
            results.append(result)
        
        # Bybit配置
        if config.bybit:
            result = await _update_config_internal(
                category="bybit",
                config=config.bybit.dict(),
                user_id=current_user_obj.id,
                validate_before_save=True,
                db=db
            )
            results.append(result)
        
        # 交易参数
        if config.trading:
            result = await _update_config_internal(
                category="trading",
                config=config.trading.dict(),
                user_id=current_user_obj.id,
                validate_before_save=False,
                db=db
            )
            results.append(result)
        
        # 风险参数
        if config.risk:
            result = await _update_config_internal(
                category="risk",
                config=config.risk.dict(),
                user_id=current_user_obj.id,
                validate_before_save=False,
                db=db
            )
            results.append(result)
        
        return {
            "success": True,
            "message": "✅ 配置批量更新成功",
            "results": results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{category}/{key}")
async def delete_config(
    category: str,
    key: str,
    current_user_obj = Depends(get_current_user_for_config),
    db: Session = Depends(get_db)
):
    """
    删除配置（按用户区分）
    
    v3.3 多用户架构：只能删除自己的配置
    """
    # 要求用户必须登录
    if not current_user_obj or not current_user_obj.id:
        raise HTTPException(
            status_code=401,
            detail="需要登录才能删除配置"
        )
    
    try:
        # v3.3: 只删除当前用户的配置
        config_entry = db.query(Configuration).filter(
            Configuration.category == category,
            Configuration.key == key,
            Configuration.user_id == current_user_obj.id
        ).first()
        
        if not config_entry:
            raise HTTPException(status_code=404, detail="配置项不存在")
        
        db.delete(config_entry)
        db.commit()
        
        return {
            "success": True,
            "message": f"✅ 配置已删除: {category}.{key}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/export")
async def export_config(
    current_user_obj = Depends(get_current_user_for_config),
    db: Session = Depends(get_db)
):
    """
    导出配置（用于备份，按用户区分）
    
    v3.3 多用户架构：只能导出自己的配置
    """
    # 要求用户必须登录
    if not current_user_obj or not current_user_obj.id:
        raise HTTPException(
            status_code=401,
            detail="需要登录才能导出配置"
        )
    
    try:
        # v3.3: 只导出当前用户的配置
        configs = db.query(Configuration).filter(
            Configuration.user_id == current_user_obj.id
        ).all()
        
        export_data = {
            "export_time": datetime.utcnow().isoformat(),
            "username": current_user_obj.username,
            "configs": {}
        }
        
        for config in configs:
            category = config.category
            if category not in export_data["configs"]:
                export_data["configs"][category] = {}
            
            value = config.value
            # 敏感信息不导出明文
            if category in ["deepseek", "bybit"] and "key" in config.key.lower():
                value = "***ENCRYPTED***"
            
            export_data["configs"][category][config.key] = {
                "value": value,
                "description": config.description
            }
        
        if "bybit" in export_data["configs"]:
            raw_bybit = export_data["configs"]["bybit"]
            export_data["configs"]["bybit"] = {
                "active_environment": raw_bybit.get("active_environment", {}).get("value", "demo"),
                "environments": {
                    env.value: {
                        "api_key": raw_bybit.get(f"api_key_{env.value}", {}).get("value"),
                        "api_secret": raw_bybit.get(f"api_secret_{env.value}", {}).get("value"),
                    }
                    for env in BYBIT_ENVIRONMENTS
                    if raw_bybit.get(f"api_key_{env.value}") or raw_bybit.get(f"api_secret_{env.value}")
                }
            }
        
        return export_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/presets")
async def get_config_presets():
    """获取预设配置"""
    presets = {
        "conservative": {
            "name": "保守策略",
            "description": "低风险，适合新手",
            "trading": {
                "trading_interval": 300,
                "max_position_pct": 20,
                "min_position_pct": 5,
                "max_leverage": 5,
                "stop_loss_pct": 3,
                "take_profit_pct": 8,
                "use_trailing_stop": True
            },
            "risk": {
                "max_daily_loss": 200,
                "max_drawdown_pct": 5,
                "auto_trading": True
            }
        },
        "balanced": {
            "name": "平衡策略",
            "description": "中等风险，推荐使用",
            "trading": {
                "trading_interval": 180,
                "max_position_pct": 30,
                "min_position_pct": 3,
                "max_leverage": 10,
                "stop_loss_pct": 2,
                "take_profit_pct": 5,
                "use_trailing_stop": True
            },
            "risk": {
                "max_daily_loss": 500,
                "max_drawdown_pct": 10,
                "auto_trading": True
            }
        },
        "aggressive": {
            "name": "激进策略",
            "description": "高风险高收益",
            "trading": {
                "trading_interval": 60,
                "max_position_pct": 50,
                "min_position_pct": 10,
                "max_leverage": 20,
                "stop_loss_pct": 1.5,
                "take_profit_pct": 3,
                "use_trailing_stop": True
            },
            "risk": {
                "max_daily_loss": 1000,
                "max_drawdown_pct": 20,
                "auto_trading": True
            }
        }
    }
    
    return {
        "success": True,
        "presets": presets
    }

# ============================================================================
# 工具函数
# ============================================================================

def load_config_from_db(db: Session, user_id: int = None) -> Dict[str, Any]:
    """
    从数据库加载配置到内存（按用户）
    
    Args:
        db: 数据库会话
        user_id: 用户ID，如果为None则加载所有用户的配置（不推荐）
    
    Returns:
        配置字典
    """
    query = db.query(Configuration)
    
    # v3.3: 如果提供了user_id，只加载该用户的配置
    if user_id is not None:
        query = query.filter(Configuration.user_id == user_id)
    
    configs = query.all()
    
    result = {}
    for config in configs:
        category = config.category
        if category not in result:
            result[category] = {}
        
        value = config.value
        # 解密敏感信息
        if category in ["deepseek", "bybit"] and "key" in config.key.lower():
            try:
                value = crypto.decrypt(value)
            except:
                pass
        
        result[category][config.key] = value
    
    if "bybit" in result:
        result["bybit"] = _compose_bybit_plain(result["bybit"])
    
    return result

def save_config_to_file(config: Dict[str, Any], filepath: str):
    """保存配置到文件（备份）"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    print("配置管理API模块")
    print("功能：")
    print("- ✅ 获取配置（脱敏）")
    print("- ✅ 验证配置")
    print("- ✅ 更新配置（加密）")
    print("- ✅ 批量更新")
    print("- ✅ 导出备份")
    print("- ✅ 预设配置")

