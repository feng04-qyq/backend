# API 对接文档

## 📋 目录

- [系统概述](#系统概述)
- [快速开始](#快速开始)
- [认证与授权](#认证与授权)
- [API 端点详解](#api-端点详解)
- [数据模型](#数据模型)
- [错误处理](#错误处理)
- [WebSocket 实时推送](#websocket-实时推送)
- [前端对接示例](#前端对接示例)
- [安全注意事项](#安全注意事项)
- [常见问题](#常见问题)

---

## 系统概述

### 架构设计

本系统采用前后端分离架构，通过 RESTful API 和 WebSocket 进行通信：

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│   前端 (Next.js)│ ◄─────► │  API 桥接层      │ ◄─────► │  交易系统引擎   │
│   Port: 3000    │  HTTP   │  Port: 8000      │         │   (后台线程)    │
└─────────────────┘  WebSocket └──────────────────┘         └─────────────────┘
                              │
                              ▼
                       ┌──────────────┐
                       │  PostgreSQL  │
                       │   数据库      │
                       └──────────────┘
```

### 核心模块

1. **统一 API 桥接层** (`api_bridge_unified.py`)
   - 标准化响应格式
   - 自动适配单用户/多用户模式
   - 数据聚合与缓存
   - 兜底数据加载（交易日志）

2. **配置管理 API** (`config_manager_api.py`)
   - DeepSeek/Bybit API 密钥管理
   - 7 层加密存储
   - 客户端加密传输支持
   - 运行时环境变量同步

3. **认证模块** (`api_auth.py`)
   - JWT Token 认证
   - 用户权限管理
   - 多用户支持

### 响应格式

所有 API 端点统一使用 `StandardResponse` 格式：

```typescript
interface StandardResponse<T> {
  success: boolean          // 操作是否成功
  message: string          // 提示信息
  data?: T                 // 业务数据（可选）
  timestamp: string        // ISO 8601 时间戳
}
```

**成功响应示例**：
```json
{
  "success": true,
  "message": "操作成功",
  "data": { ... },
  "timestamp": "2025-11-01T08:00:00.000Z"
}
```

**失败响应示例**：
```json
{
  "success": false,
  "message": "错误详情",
  "timestamp": "2025-11-01T08:00:00.000Z"
}
```

---

## 快速开始

### 1. 基础配置

**后端地址**（根据部署环境调整）：
```typescript
// 开发环境
const API_BASE_URL = "http://localhost:8000"

// 生产环境
const API_BASE_URL = "http://your-server-ip:8000"
```

**前端环境变量**（`crypto-trading-platform/.env.local`）：
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 2. 认证流程

```typescript
// 1. 登录获取 Token
const loginResponse = await fetch(`${API_BASE_URL}/api/auth/login`, {
  method: "POST",
  headers: { "Content-Type": "application/x-www-form-urlencoded" },
  body: new URLSearchParams({
    username: "admin",
    password: "admin123"
  })
})

const { access_token } = await loginResponse.json()

// 2. 存储 Token（建议使用 localStorage 或 secure cookie）
localStorage.setItem("token", access_token)

// 3. 后续请求携带 Token
const headers = {
  "Authorization": `Bearer ${access_token}`,
  "Content-Type": "application/json"
}
```

### 3. 使用前端 API 客户端

项目已封装统一的 API 客户端，位于 `crypto-trading-platform/lib/api/`：

```typescript
import { apiClient } from "@/lib/api/client"
import { getBalance, getTrades } from "@/lib/api/trading"
import { getConfig, updateConfig } from "@/lib/api/config"

// 使用示例
const balance = await getBalance()
const trades = await getTrades({ limit: 20 })
const config = await getConfig()
```

---

## 认证与授权

### 登录接口

**端点**：`POST /api/auth/login`

**请求格式**：`application/x-www-form-urlencoded`

```typescript
// 请求
POST /api/auth/login
Content-Type: application/x-www-form-urlencoded

username=admin&password=admin123
```

**响应**：
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800,
  "username": "admin",
  "is_admin": true,
  "scopes": ["read", "write", "admin"]
}
```

### 获取当前用户

**端点**：`GET /api/auth/me`

**请求头**：
```
Authorization: Bearer <token>
```

**响应**：
```json
{
  "id": 1,
  "username": "admin",
  "is_admin": true,
  "scopes": ["read", "write", "admin"]
}
```

### Token 刷新

**端点**：`POST /api/auth/refresh`

**请求头**：
```
Authorization: Bearer <token>
```

**响应**：与登录接口相同

### 权限说明

- **普通用户** (`scopes: ["read", "write"]`)：可查看和配置自己的交易设置
- **管理员** (`scopes: ["read", "write", "admin"]`)：可管理所有用户和系统配置

---

## API 端点详解

### 交易系统控制

#### 1. 启动交易系统

**端点**：`POST /api/trading/start`

**参数**（Query）：
- `mode` (可选): 运行模式 - `demo` | `testnet` | `live`，默认 `demo`
- `symbols` (可选): 交易对数组，例如 `["BTCUSDT", "ETHUSDT"]`

**请求示例**：
```typescript
POST /api/trading/start?mode=demo&symbols=BTCUSDT&symbols=ETHUSDT
Authorization: Bearer <token>
```

**响应**：
```json
{
  "success": true,
  "message": "交易系统启动成功",
  "data": {
    "success": true,
    "message": "交易系统已启动",
    "mode": "demo",
    "symbols": ["BTCUSDT", "ETHUSDT"]
  }
}
```

#### 2. 停止交易系统

**端点**：`POST /api/trading/stop`

**请求示例**：
```typescript
POST /api/trading/stop
Authorization: Bearer <token>
```

**响应**：
```json
{
  "success": true,
  "message": "交易系统已停止",
  "data": {
    "success": true,
    "message": "交易系统已停止"
  }
}
```

#### 3. 重启交易系统

**端点**：`POST /api/trading/restart`

**参数**（Query）：与启动接口相同

#### 4. 获取系统状态

**端点**：`GET /api/trading/status`

**响应**：
```json
{
  "success": true,
  "data": {
    "is_running": true,
    "mode": "demo",
    "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    "total_trades": 42,
    "active_positions": 2,
    "total_pnl": 1250.50
  }
}
```

### 账户与余额

#### 1. 获取账户余额

**端点**：`GET /api/balance`

**响应**：
```json
{
  "success": true,
  "data": {
    "balance": 10000.00,
    "available_balance": 8500.00,
    "unrealized_pnl": 250.50,
    "realized_pnl": 1250.00,
    "currency": "USDT"
  }
}
```

**数据来源优先级**：
1. 数据库账户快照（最新）
2. 正在运行的交易系统（实时）
3. 本地交易日志（兜底）

### 持仓管理

#### 1. 获取持仓列表

**端点**：`GET /api/positions` 或 `GET /api/positions/live`

**参数**（Query）：
- `symbol` (可选): 筛选特定交易对

**响应**：
```json
{
  "success": true,
  "data": {
    "positions": [
      {
        "symbol": "BTCUSDT",
        "side": "Buy",
        "size": 0.1,
        "entry_price": 45000.00,
        "current_price": 45250.00,
        "unrealized_pnl": 25.00,
        "leverage": 10,
        "stop_loss": 44500.00,
        "take_profit": [46000.00, 47000.00],
        "margin": 450.00
      }
    ]
  }
}
```

#### 2. 平仓

**端点**：`POST /api/positions/{symbol}/close`

**请求示例**：
```typescript
POST /api/positions/BTCUSDT/close
Authorization: Bearer <token>
```

### 交易历史

#### 1. 获取交易记录

**端点**：`GET /api/trades` 或 `GET /api/trades/live`

**参数**（Query）：
- `limit` (可选): 返回数量，默认 50，最大 200
- `offset` (可选): 偏移量，默认 0
- `status` (可选): 筛选状态 - `open` | `closed`
- `symbol` (可选): 筛选交易对

**响应**：
```json
{
  "success": true,
  "data": {
    "trades": [
      {
        "trade_id": "trade_123456",
        "symbol": "BTCUSDT",
        "side": "Buy",
        "entry_price": 45000.00,
        "close_price": 45250.00,
        "position_size": 0.1,
        "pnl": 25.00,
        "pnl_pct": 0.56,
        "status": "closed",
        "entry_time": "2025-11-01T08:00:00Z",
        "close_time": "2025-11-01T09:30:00Z",
        "entry_reason": "AI决策：突破阻力位",
        "close_reason": "止盈"
      }
    ],
    "total": 42
  }
}
```

#### 2. 获取交易详情

**端点**：`GET /api/trades/{trade_id}`

### 仪表盘聚合数据

#### 获取仪表盘概览

**端点**：`GET /api/dashboard/overview`

**参数**（Query）：
- `limit` (可选): 最近交易数量，默认 30

**说明**：此接口聚合了余额、系统状态、统计数据、最近交易，**推荐优先使用**以减少 HTTP 请求。

**响应**：
```json
{
  "success": true,
  "data": {
    "balance": {
      "balance": 10000.00,
      "available_balance": 8500.00,
      "unrealized_pnl": 250.50,
      "realized_pnl": 1250.00
    },
    "system_status": {
      "is_running": true,
      "mode": "demo",
      "symbols": ["BTCUSDT", "ETHUSDT"],
      "total_trades": 42,
      "active_positions": 2,
      "total_pnl": 1250.50
    },
    "analytics_summary": {
      "total_trades": 42,
      "win_rate": 65.5,
      "total_pnl": 1250.50,
      "avg_pnl": 29.77,
      "best_trade": 150.00,
      "worst_trade": -50.00,
      "winning_trades": 28,
      "losing_trades": 14
    },
    "recent_trades": [ ... ]
  }
}
```

**缓存策略**：TTL 5 秒，相同用户和 limit 参数在 5 秒内的请求返回缓存结果。

### AI 决策记录

#### 获取 AI 决策历史

**端点**：`GET /api/ai/decisions`

**参数**（Query）：
- `limit` (可选): 返回数量，默认 50
- `offset` (可选): 偏移量，默认 0
- `action` (可选): 筛选动作 - `LONG` | `SHORT` | `CLOSE` | `HOLD`

**响应**：
```json
{
  "success": true,
  "data": {
    "decisions": [
      {
        "id": 123,
        "decision_id": "decision_123456",
        "action": "LONG",
        "target_symbol": "BTCUSDT",
        "confidence": 85,
        "reason": "技术指标显示突破信号",
        "market_state": "trending_up",
        "created_at": "2025-11-01T08:00:00Z",
        "executed": true,
        "execution_time": "2025-11-01T08:00:15Z"
      }
    ],
    "total": 150
  }
}
```

### 统计数据

#### 获取统计摘要

**端点**：`GET /api/statistics/summary` 或 `GET /api/analytics/statistics`

**参数**（Query）：
- `period` (可选): 统计周期 - `7d` | `30d` | `90d` | `all`，默认 `30d`

**响应**：
```json
{
  "success": true,
  "data": {
    "total_trades": 42,
    "win_rate": 65.5,
    "total_pnl": 1250.50,
    "avg_pnl": 29.77,
    "best_trade": 150.00,
    "worst_trade": -50.00,
    "winning_trades": 28,
    "losing_trades": 14,
    "sharpe_ratio": 1.25,
    "max_drawdown": -5.2
  }
}
```

### 配置管理

#### 1. 获取所有配置

**端点**：`GET /api/config` 或 `GET /api/config/all`

**响应**（敏感字段已脱敏）：
```json
{
  "success": true,
  "data": {
    "deepseek": {
      "api_key": "sk-QrWi****xxx",
      "model": "deepseek-chat",
      "system_prompt": "你是一个专业的加密货币交易助手..."
    },
    "bybit": {
      "api_key_demo": "QrWi****xxx",
      "api_key_testnet": null,
      "api_key_mainnet": null,
      "active_environment": "demo"
    },
    "trading": {
      "interval": 180,
      "max_position_pct": 30,
      "max_leverage": 15,
      "enable_trailing_stop": true,
      "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    },
    "risk": {
      "max_drawdown_pct": 10,
      "stop_loss_pct": 2
    }
  }
}
```

#### 2. 验证 DeepSeek API

**端点**：`POST /api/config/validate/deepseek`

**请求体**（支持客户端加密）：
```json
{
  "encrypted": true,
  "payload": {
    "version": 1,
    "alg": "AES-256-GCM",
    "salt": "...",
    "iv": "...",
    "data": "...",
    "tag": "..."
  }
}
```

**或明文格式**（开发环境）：
```json
{
  "api_key": "sk-...",
  "model": "deepseek-chat"
}
```

**响应**：
```json
{
  "valid": true,
  "message": "✅ DeepSeek API验证成功",
  "details": {
    "model": "deepseek-chat",
    "usage": "1234/1000000"
  }
}
```

#### 3. 验证 Bybit API

**端点**：`POST /api/config/validate/bybit`

**请求体**（支持客户端加密）：
```json
{
  "encrypted": true,
  "payload": { ... }
}
```

**或明文格式**：
```json
{
  "api_key": "QrWifZlOorEiJ6qqAd",
  "api_secret": "9TSAc2sQOq2xKJ4AJ8Rn5eDu66LZg7vJXvQT",
  "environment": "demo"  // demo | testnet | mainnet
}
```

**响应**：
```json
{
  "valid": true,
  "message": "✅ Bybit API验证成功",
  "details": {
    "environment": "模拟盘",
    "balance": "$10,000.00",
    "account_type": "UNIFIED",
    "endpoint": "https://api-demo.bybit.com"
  }
}
```

**常见错误码**：
- `10003`: API key 无效
- `10006`: 速率限制（视为验证通过，但需稍后重试）

#### 4. 更新配置

**端点**：`PUT /api/config/{category}`

**类别**：`deepseek` | `bybit` | `trading` | `risk`

**请求示例**（更新交易参数）：
```typescript
PUT /api/config/trading
Authorization: Bearer <token>
Content-Type: application/json

{
  "interval": 300,
  "max_position_pct": 25,
  "max_leverage": 10,
  "enable_trailing_stop": true,
  "symbols": ["BTCUSDT", "ETHUSDT", "DOGEUSDT"]
}
```

**说明**：
- `symbols` 字段支持输入简写（如 `BTC`），系统自动补全为 `BTCUSDT`
- 若选择非默认交易对（非 BTC/ETH/SOL），系统会要求先自定义 AI 系统提示词

**响应**：
```json
{
  "success": true,
  "message": "配置更新成功",
  "data": {
    "category": "trading",
    "updated_keys": ["interval", "max_position_pct", "symbols"]
  }
}
```

### 用户管理（管理员）

#### 1. 获取用户列表

**端点**：`GET /api/users`

**权限**：管理员

**响应**：
```json
{
  "success": true,
  "data": {
    "users": [
      {
        "id": 1,
        "username": "admin",
        "is_admin": true,
        "created_at": "2025-10-01T00:00:00Z"
      }
    ],
    "total": 1
  }
}
```

#### 2. 创建用户

**端点**：`POST /api/users`

**权限**：管理员

**请求体**：
```json
{
  "username": "newuser",
  "password": "secure_password",
  "is_admin": false
}
```

### 健康检查

**端点**：`GET /health` 或 `GET /api/health`

**响应**：
```json
{
  "status": "healthy",
  "timestamp": "2025-11-01T08:00:00Z",
  "version": "3.1.0"
}
```

---

## 数据模型

### TradingSystemStatus

```typescript
interface TradingSystemStatus {
  is_running: boolean        // 系统是否运行中
  mode: "demo" | "testnet" | "live"
  symbols: string[]          // 交易对列表
  total_trades: number       // 总交易数
  active_positions: number   // 当前持仓数
  total_pnl: number         // 总盈亏
}
```

### PositionInfo

```typescript
interface PositionInfo {
  symbol: string            // 交易对，如 "BTCUSDT"
  side: "Buy" | "Sell"      // 方向
  size: number              // 持仓数量
  entry_price: number        // 开仓价格
  current_price?: number     // 当前价格
  unrealized_pnl?: number    // 未实现盈亏
  leverage: number          // 杠杆倍数
  stop_loss?: number         // 止损价格
  take_profit?: number[]     // 止盈价格数组
  margin?: number            // 占用保证金
}
```

### TradeInfo

```typescript
interface TradeInfo {
  trade_id: string          // 交易ID
  symbol: string            // 交易对
  side: "Buy" | "Sell"      // 方向
  entry_price: number       // 开仓价格
  close_price?: number      // 平仓价格
  position_size: number     // 持仓大小
  pnl?: number              // 盈亏
  pnl_pct?: number          // 盈亏百分比
  status: "open" | "closed" // 状态
  entry_time: string        // ISO 8601 时间戳
  close_time?: string        // ISO 8601 时间戳
  entry_reason?: string      // 开仓理由
  close_reason?: string      // 平仓理由
}
```

### DashboardOverview

```typescript
interface DashboardOverview {
  balance: {
    balance: number
    available_balance: number
    unrealized_pnl: number
    realized_pnl: number
  }
  system_status: TradingSystemStatus
  analytics_summary: {
    total_trades: number
    win_rate: number
    total_pnl: number
    avg_pnl: number
    best_trade: number
    worst_trade: number
    winning_trades: number
    losing_trades: number
  }
  recent_trades: TradeInfo[]
}
```

---

## 错误处理

### HTTP 状态码

- `200 OK`: 请求成功
- `400 Bad Request`: 请求参数错误
- `401 Unauthorized`: 未认证或 Token 失效
- `403 Forbidden`: 权限不足
- `404 Not Found`: 资源不存在
- `500 Internal Server Error`: 服务器内部错误

### 错误响应格式

```json
{
  "success": false,
  "message": "错误详情描述",
  "detail": "详细错误信息（可选）",
  "timestamp": "2025-11-01T08:00:00Z"
}
```

### 常见错误场景

#### 1. Token 过期

**响应**：`401 Unauthorized`
```json
{
  "detail": "Token expired"
}
```

**处理**：重新登录获取新 Token

#### 2. 配置验证失败

**响应**：
```json
{
  "valid": false,
  "message": "❌ API验证失败: API key is invalid. (ErrCode: 10003)",
  "details": {
    "error_code": 10003,
    "suggestion": "请确认所选环境与密钥一致..."
  }
}
```

#### 3. 系统运行中

**响应**：`400 Bad Request`
```json
{
  "success": false,
  "message": "交易系统已在运行中，请先停止"
}
```

### 前端错误处理示例

```typescript
import { toast } from "sonner"

async function handleApiCall<T>(
  apiCall: () => Promise<T>
): Promise<T | null> {
  try {
    return await apiCall()
  } catch (error: any) {
    const message = error.response?.data?.detail 
      || error.response?.data?.message 
      || error.message 
      || "操作失败"
    
    toast.error(message)
    console.error("API调用失败:", error)
    return null
  }
}

// 使用示例
const balance = await handleApiCall(() => getBalance())
```

---

## WebSocket 实时推送

### 连接方式

**端点**：`ws://localhost:8000/ws?token=<jwt_token>`

**连接示例**（前端）：
```typescript
import { useWebSocket } from "@/lib/hooks/useWebSocket"

function Dashboard() {
  const ws = useWebSocket() // 自动连接，Token 从 localStorage 读取
  
  // 监听事件
  useWebSocketEvent("account_update", (data) => {
    console.log("账户更新:", data)
  })
  
  useWebSocketEvent("trade_open", (data) => {
    toast.success(`开仓: ${data.symbol}`)
  })
}
```

### 事件类型

| 事件类型 | 说明 | 数据格式 |
|---------|------|---------|
| `connected` | 连接成功 | `{ message: "Connected" }` |
| `account_update` | 账户余额更新 | `{ balance, available_balance, unrealized_pnl, realized_pnl }` |
| `position_update` | 持仓更新 | `{ positions: PositionInfo[] }` |
| `trade_open` | 开仓通知 | `{ trade_id, symbol, side, entry_price, ... }` |
| `trade_close` | 平仓通知 | `{ trade_id, symbol, pnl, close_price, ... }` |
| `ai_decision` | AI 决策 | `{ action, target_symbol, confidence, reason }` |
| `risk_warning` | 风险警告 | `{ message, severity, symbol? }` |
| `trailing_stop_update` | 移动止损更新 | `{ symbol, new_stop_loss, trigger_price }` |
| `system_status` | 系统状态更新 | `TradingSystemStatus` |

### WebSocket Hook 使用示例

```typescript
import { useWebSocket, useWebSocketEvent } from "@/lib/hooks/useWebSocket"
import { toast } from "sonner"

export default function TradingDashboard() {
  const ws = useWebSocket()
  
  // 监听账户更新
  useWebSocketEvent("account_update", (data) => {
    setBalance(data.balance)
  })
  
  // 监听开仓
  useWebSocketEvent("trade_open", (data) => {
    toast.success(`开仓成功：${data.symbol} ${data.side}`)
    refreshTrades()
  })
  
  // 监听平仓
  useWebSocketEvent("trade_close", (data) => {
    const icon = data.pnl > 0 ? "🎉" : "😢"
    toast(`${icon} 平仓：${data.symbol}，盈亏 $${data.pnl.toFixed(2)}`)
    refreshTrades()
  })
  
  // 监听 AI 决策
  useWebSocketEvent("ai_decision", (data) => {
    toast.info(`AI决策：${data.action} ${data.target_symbol}`)
  })
  
  // 监听风险警告
  useWebSocketEvent("risk_warning", (data) => {
    toast.error(`风险警告：${data.message}`, { duration: 8000 })
  })
  
  return <div>...</div>
}
```

---

## 前端对接示例

### 1. API 客户端配置

**文件**：`crypto-trading-platform/lib/api/client.ts`

```typescript
import axios from "axios"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    "Content-Type": "application/json",
  },
})

// 请求拦截器：自动添加 Token
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("token")
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：统一错误处理
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token 过期，清除并跳转登录
      localStorage.removeItem("token")
      window.location.href = "/login"
    }
    return Promise.reject(error)
  }
)
```

### 2. 登录示例

```typescript
import { apiClient } from "@/lib/api/client"

async function login(username: string, password: string) {
  const formData = new URLSearchParams()
  formData.append("username", username)
  formData.append("password", password)
  
  const response = await apiClient.post("/api/auth/login", formData, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" }
  })
  
  const { access_token, username: user, is_admin } = response.data
  
  // 存储 Token 和用户信息
  localStorage.setItem("token", access_token)
  useUserStore.getState().setToken(access_token)
  useUserStore.getState().setUser({ username: user, is_admin, scopes: [] })
  
  return response.data
}
```

### 3. 获取仪表盘数据

```typescript
import { getDashboardOverview } from "@/lib/api/trading"

async function loadDashboard() {
  try {
    const overview = await getDashboardOverview(30)
    
    // 更新状态
    setBalance(overview.balance)
    setSystemStatus(overview.system_status)
    setAnalytics(overview.analytics_summary)
    setRecentTrades(overview.recent_trades)
  } catch (error) {
    console.error("加载仪表盘失败:", error)
    toast.error("加载数据失败")
  }
}
```

### 4. 配置管理示例

```typescript
import { getConfig, updateConfig, validateBybitAPI } from "@/lib/api/config"

// 加载配置
async function loadConfig() {
  const config = await getConfig()
  setDeepSeekConfig(config.deepseek)
  setBybitConfig(config.bybit)
  setTradingConfig(config.trading)
}

// 验证 Bybit API
async function validateBybit() {
  setIsValidating(true)
  try {
    const result = await validateBybitAPI({
      api_key: bybitApiKey,
      api_secret: bybitApiSecret,
      environment: "demo"
    })
    
    if (result.success) {
      toast.success(result.message || "验证成功")
      // 验证成功后自动保存
      await updateConfig({
        category: "bybit",
        config: {
          api_key: bybitApiKey,
          api_secret: bybitApiSecret,
          environment: "demo"
        }
      })
    } else {
      toast.error(result.error || "验证失败")
    }
  } finally {
    setIsValidating(false)
  }
}

// 更新交易参数
async function saveTradingParams() {
  await updateConfig({
    category: "trading",
    config: {
      interval: tradingInterval,
      max_position_pct: maxPosition,
      max_leverage: maxLeverage,
      enable_trailing_stop: trailingStop,
      symbols: ["BTC", "ETH", "SOL"] // 支持简写
    }
  })
  toast.success("保存成功")
}
```

### 5. 交易系统控制示例

```typescript
import { startTradingSystem, stopTradingSystem, getSystemStatus } from "@/lib/api/trading"

// 启动交易系统
async function startSystem() {
  try {
    await startTradingSystem({
      mode: "demo",
      symbols: ["BTCUSDT", "ETHUSDT"]
    })
    toast.success("交易系统已启动")
    refreshStatus()
  } catch (error) {
    toast.error("启动失败：" + error.message)
  }
}

// 停止交易系统
async function stopSystem() {
  try {
    await stopTradingSystem()
    toast.success("交易系统已停止")
    refreshStatus()
  } catch (error) {
    toast.error("停止失败：" + error.message)
  }
}

// 轮询获取状态
useEffect(() => {
  const interval = setInterval(async () => {
    const status = await getSystemStatus()
    setSystemStatus(status)
  }, 5000) // 每 5 秒刷新
  
  return () => clearInterval(interval)
}, [])
```

---

## 安全注意事项

### 1. Token 安全

- ✅ **存储**：使用 `localStorage` 或 `sessionStorage`（生产环境建议使用 HTTP-only Cookie）
- ✅ **过期处理**：Token 有效期 30 分钟，过期后自动跳转登录
- ✅ **传输**：所有请求通过 HTTPS（生产环境）

### 2. API 密钥加密传输

系统支持客户端加密传输 API 密钥：

```typescript
// 前端自动加密（lib/security/encryption.ts）
import { encryptSensitivePayload } from "@/lib/security/encryption"

// 验证 API 时自动加密
const payload = await encryptSensitivePayload({
  api_key: "sk-...",
  api_secret: "..."
})

// 后端自动解密并验证
```

**加密算法**：
- AES-256-GCM
- 密钥派生：PBKDF2（120,000 次迭代）
- 密钥来源：用户 JWT Token（不暴露 RSA 公钥）

### 3. 后端加密存储

所有敏感配置在数据库中使用 **7 层加密**存储：
1. PBKDF2 密钥派生
2. AES-256-GCM
3. RSA-4096
4. Fernet 双重加密
5. 自定义混淆
6. Base85 编码
7. HMAC 完整性校验

### 4. CORS 配置

**开发环境**：允许所有来源（便于调试）

**生产环境**：应限制为特定域名：
```python
allow_origins=[
    "https://your-frontend-domain.com",
]
```

### 5. 权限控制

- 普通用户只能访问和修改自己的配置
- 管理员可管理所有用户
- 交易系统控制需要管理员权限（部分功能）

---

## 常见问题

### Q1: Token 过期后如何处理？

**A**: 前端应检测 401 响应，自动清除 Token 并跳转登录页：

```typescript
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("token")
      window.location.href = "/login"
    }
    return Promise.reject(error)
  }
)
```

### Q2: Bybit API 验证失败（ErrCode: 10003）

**可能原因**：
1. API Key 与所选环境不匹配（demo/testnet/mainnet）
2. API Key 未启用 Unified 账户权限
3. API Key 已失效或被撤销

**解决方案**：
1. 确认环境选择正确
2. 在 Bybit 后台检查 API Key 权限设置
3. 重新生成 API Key 并验证

### Q3: 仪表盘数据不更新

**检查项**：
1. WebSocket 连接是否正常
2. Token 是否有效
3. 后端服务是否正常运行

**调试方法**：
```typescript
// 检查 WebSocket 连接
const ws = useWebSocket()
console.log("WS状态:", ws?.readyState) // 1 = OPEN

// 手动刷新数据
const refresh = async () => {
  const overview = await getDashboardOverview()
  console.log("最新数据:", overview)
}
```

### Q4: 更新交易对后提示需要修改 AI 提示词

**说明**：系统默认支持 BTC/ETH/SOL。若选择其他交易对（如 DOGE），需自定义 AI 系统提示词以适配新币种。

**解决方案**：
1. 在设置页打开 "AI 系统提示词" 编辑器
2. 根据新交易对调整提示词（例如：添加 DOGE 相关策略）
3. 保存后即可启动交易系统

### Q5: 多用户模式 vs 单用户模式

**单用户模式**：
- 所有用户共享同一交易系统实例
- 适用于个人使用或小团队

**多用户模式**：
- 每个用户拥有独立的交易系统实例
- 适用于多租户 SaaS 场景
- 自动根据部署环境切换

### Q6: 如何查看实时日志？

**后端日志**：
```bash
# 查看 uvicorn 日志
tail -f logs/api_server.log

# 查看交易系统日志
tail -f logs/trading_system.log
```

**前端调试**：
```typescript
// 开启详细日志
localStorage.setItem("DEBUG", "true")

// 在浏览器控制台查看 WebSocket 消息
```

---

## 附录

### API 端点速查表

| 类别 | 方法 | 端点 | 认证 |
|-----|------|------|------|
| **认证** | POST | `/api/auth/login` | ❌ |
| | GET | `/api/auth/me` | ✅ |
| | POST | `/api/auth/refresh` | ✅ |
| **交易系统** | POST | `/api/trading/start` | ✅ |
| | POST | `/api/trading/stop` | ✅ |
| | POST | `/api/trading/restart` | ✅ |
| | GET | `/api/trading/status` | ✅ |
| **账户** | GET | `/api/balance` | ✅ |
| **持仓** | GET | `/api/positions` | ✅ |
| | POST | `/api/positions/{symbol}/close` | ✅ |
| **交易** | GET | `/api/trades` | ✅ |
| **仪表盘** | GET | `/api/dashboard/overview` | ✅ |
| **AI决策** | GET | `/api/ai/decisions` | ✅ |
| **统计** | GET | `/api/statistics/summary` | ✅ |
| **配置** | GET | `/api/config` | ✅ |
| | PUT | `/api/config/{category}` | ✅ |
| | POST | `/api/config/validate/deepseek` | ✅ |
| | POST | `/api/config/validate/bybit` | ✅ |
| **用户** | GET | `/api/users` | ✅ Admin |
| | POST | `/api/users` | ✅ Admin |
| **健康检查** | GET | `/health` | ❌ |

### 环境变量参考

**后端** (`.env`):
```env
# 数据库
DATABASE_URL=postgresql://user:password@host:5432/dbname

# JWT
JWT_SECRET_KEY=your-secret-key

# API Keys（运行时从数据库加载）
DEEPSEEK_API_KEY=
BYBIT_API_KEY=
BYBIT_API_SECRET=
```

**前端** (`.env.local`):
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

**文档版本**: v1.0  
**最后更新**: 2025-11-01

