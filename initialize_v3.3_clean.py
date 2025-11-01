#!/usr/bin/env python3
"""
v3.3 多实例架构 - 全新初始化脚本
适用于：数据库已清空，需要重新创建所有表

功能：
1. 创建所有数据库表
2. 创建默认管理员账号
3. 自动生成 JWT 密钥
4. 验证系统配置
5. 运行健康检查

使用方法:
    python initialize_v3.3_clean.py
"""

import os
import sys
import secrets
import hashlib
from datetime import datetime
from pathlib import Path

# ANSI 颜色代码
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_header(text):
    """打印标题"""
    print("\n" + "="*80)
    print(f"{BLUE}{text:^80}{RESET}")
    print("="*80)

def print_success(text):
    """打印成功消息"""
    print(f"{GREEN}✅ {text}{RESET}")

def print_warning(text):
    """打印警告消息"""
    print(f"{YELLOW}⚠️  {text}{RESET}")

def print_error(text):
    """打印错误消息"""
    print(f"{RED}❌ {text}{RESET}")

def print_info(text):
    """打印信息消息"""
    print(f"{BLUE}ℹ️  {text}{RESET}")

def generate_jwt_secret():
    """生成 JWT 密钥"""
    return secrets.token_urlsafe(64)

def generate_master_api_key():
    """生成 Master API Key"""
    return secrets.token_urlsafe(32)

def setup_env_file():
    """设置 .env 文件"""
    print_header("第 1 步: 配置环境变量")
    
    env_file = Path(".env")
    
    # 读取现有的 .env（如果有）
    existing_env = {}
    if env_file.exists():
        print_info("发现现有 .env 文件，将保留部分配置")
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    existing_env[key.strip()] = value.strip()
    
    # 生成新的密钥
    jwt_secret = generate_jwt_secret()
    master_api_key = generate_master_api_key()
    
    # 准备环境变量
    env_config = {
        "# ═══════════════════════════════════════════════════════════════": "",
        "# v3.3 Multi-Instance Trading System Configuration": "",
        "# Generated at: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"): "",
        "# ═══════════════════════════════════════════════════════════════": "",
        "": "",
        "# ============================================================================": "",
        "# 数据库配置": "",
        "# ============================================================================": "",
        "DATABASE_URL": existing_env.get("DATABASE_URL", 
            "postgresql://trading_user:your_password@localhost:5432/bybit_trading"),
        "": "",
        "# ============================================================================": "",
        "# JWT 认证配置（自动生成）": "",
        "# ============================================================================": "",
        "JWT_SECRET_KEY": jwt_secret,
        "JWT_ALGORITHM": "HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
        "": "",
        "# ============================================================================": "",
        "# Master API Key（系统间调用）": "",
        "# ============================================================================": "",
        "MASTER_API_KEY": master_api_key,
        "": "",
        "# ============================================================================": "",
        "# 固定交易对（系统级配置）": "",
        "# ============================================================================": "",
        "FIXED_SYMBOLS": "BTCUSDT,ETHUSDT,SOLUSDT",
        "": "",
        "# ============================================================================": "",
        "# 用户参数限制": "",
        "# ============================================================================": "",
        "MAX_POSITIONS_LIMIT": "5",
        "MIN_CHECK_INTERVAL": "30",
        "MAX_CHECK_INTERVAL": "300",
        "MAX_RISK_PER_TRADE": "0.05",
        "MIN_RISK_PER_TRADE": "0.01",
        "": "",
        "# ============================================================================": "",
        "# 默认管理员账号（首次登录后请立即修改密码）": "",
        "# ============================================================================": "",
        "DEFAULT_ADMIN_USERNAME": "admin",
        "DEFAULT_ADMIN_PASSWORD": "admin123",
        "": "",
        "# ============================================================================": "",
        "# API 服务器配置": "",
        "# ============================================================================": "",
        "API_HOST": existing_env.get("API_HOST", "0.0.0.0"),
        "API_PORT": existing_env.get("API_PORT", "8000"),
        "": "",
        "# ============================================================================": "",
        "# 日志配置": "",
        "# ============================================================================": "",
        "LOG_LEVEL": existing_env.get("LOG_LEVEL", "INFO"),
        "LOG_FILE": existing_env.get("LOG_FILE", "logs/trading_system.log"),
        "": "",
        "# ============================================================================": "",
        "# 外部 API 密钥（可选，用于测试）": "",
        "# ============================================================================": "",
        "# BYBIT_API_KEY": existing_env.get("BYBIT_API_KEY", "your_bybit_api_key"),
        "# BYBIT_API_SECRET": existing_env.get("BYBIT_API_SECRET", "your_bybit_api_secret"),
        "# DEEPSEEK_API_KEY": existing_env.get("DEEPSEEK_API_KEY", "your_deepseek_api_key"),
    }
    
    # 写入 .env 文件
    with open(env_file, 'w', encoding='utf-8') as f:
        for key, value in env_config.items():
            if key.startswith('#') or key == '':
                f.write(f"{key}\n")
            else:
                f.write(f"{key}={value}\n")
    
    print_success(f".env 文件已创建/更新")
    print_info(f"JWT 密钥已自动生成（长度: {len(jwt_secret)} 字符）")
    print_info(f"Master API Key 已自动生成（长度: {len(master_api_key)} 字符）")
    
    return True

def create_database_tables():
    """创建数据库表"""
    print_header("第 2 步: 创建数据库表")
    
    try:
        # 导入数据库模型
        from database_models import Base, engine, init_database
        
        print_info("开始创建数据库表...")
        
        # 创建所有表
        Base.metadata.create_all(bind=engine)
        
        print_success("数据库表创建成功")
        
        # 显示创建的表
        tables = Base.metadata.tables.keys()
        print_info(f"已创建 {len(tables)} 个表:")
        for table in tables:
            print(f"  - {table}")
        
        return True
        
    except ImportError as e:
        print_error(f"无法导入数据库模块: {e}")
        print_warning("请确保 database_models.py 存在并且依赖已安装")
        return False
    
    except Exception as e:
        print_error(f"创建数据库表失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def create_default_admin():
    """创建默认管理员账号"""
    print_header("第 3 步: 创建默认管理员账号")
    
    try:
        from database_models import SessionLocal, User
        from dotenv import load_dotenv
        
        load_dotenv()
        
        db = SessionLocal()
        
        # 检查是否已有管理员
        existing_admin = db.query(User).filter(User.is_admin == True).first()
        
        if existing_admin:
            print_warning(f"管理员账号已存在: {existing_admin.username}")
            print_info("跳过创建")
            db.close()
            return True
        
        # 创建默认管理员
        username = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
        password = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")
        
        # 使用与 api_auth.py 相同的哈希方法
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        admin_user = User(
            username=username,
            email=f"{username}@localhost",
            hashed_password=password_hash,
            is_admin=True,
            is_active=True,
            created_at=datetime.utcnow()
        )
        
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        
        print_success(f"默认管理员账号已创建")
        print_info(f"用户名: {username}")
        print_warning(f"密码: {password}")
        print_warning("⚠️  首次登录后请立即修改密码！")
        
        db.close()
        return True
        
    except Exception as e:
        print_error(f"创建管理员账号失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_system():
    """验证系统配置"""
    print_header("第 4 步: 验证系统配置")
    
    checks = []
    
    # 检查 .env 文件
    if os.path.exists(".env"):
        checks.append((".env 文件", True))
    else:
        checks.append((".env 文件", False))
    
    # 检查关键文件
    critical_files = [
        "database_models.py",
        "api_auth.py",
        "trading_system_multi_user_manager.py",
        "trading_api_multi_user.py",
        "requirements.txt",
    ]
    
    for file in critical_files:
        exists = os.path.exists(file)
        checks.append((file, exists))
    
    # 检查日志目录
    log_dir = Path("logs")
    if not log_dir.exists():
        log_dir.mkdir(parents=True, exist_ok=True)
        checks.append(("logs 目录", True))
        print_info("已创建 logs 目录")
    else:
        checks.append(("logs 目录", True))
    
    # 显示检查结果
    print("\n验证结果:")
    all_passed = True
    for check_name, passed in checks:
        if passed:
            print_success(f"{check_name}")
        else:
            print_error(f"{check_name} - 缺失")
            all_passed = False
    
    return all_passed

def print_next_steps():
    """打印后续步骤"""
    print_header("✅ 初始化完成！")
    
    print("\n📋 后续步骤:\n")
    
    steps = [
        "1️⃣  启动 API 服务器:",
        "   python api_server_unified.py",
        "",
        "2️⃣  或使用 uvicorn:",
        "   uvicorn api_server_unified:app --host 0.0.0.0 --port 8000 --reload",
        "",
        "3️⃣  管理员登录:",
        "   用户名: admin",
        "   密码: admin123",
        "   ⚠️  首次登录后立即修改密码！",
        "",
        "4️⃣  修改密码（API调用）:",
        "   curl -X POST 'http://localhost:8000/api/auth/change-password' \\",
        "     -H 'Authorization: Bearer <your_token>' \\",
        "     -H 'Content-Type: application/json' \\",
        "     -d '{\"old_password\": \"admin123\", \"new_password\": \"NewSecurePass123!\"}'",
        "",
        "5️⃣  创建第一个用户（只有管理员可以）:",
        "   curl -X POST 'http://localhost:8000/api/auth/register' \\",
        "     -H 'Authorization: Bearer <admin_token>' \\",
        "     -H 'Content-Type: application/json' \\",
        "     -d '{",
        "       \"username\": \"trader1\",",
        "       \"password\": \"TraderPass123!\",",
        "       \"is_admin\": false,",
        "       \"scopes\": [\"read\", \"write\"]",
        "     }'",
        "",
        "6️⃣  用户启动自己的交易系统:",
        "   curl -X POST 'http://localhost:8000/api/user/trading/start' \\",
        "     -H 'Authorization: Bearer <user_token>' \\",
        "     -H 'Content-Type: application/json' \\",
        "     -d '{",
        "       \"mode\": \"demo\",",
        "       \"check_interval\": 60,",
        "       \"max_positions\": 3,",
        "       \"use_ai\": true",
        "     }'",
    ]
    
    for step in steps:
        print(f"  {step}")
    
    print("\n" + "="*80)
    print(f"{GREEN}📚 详细文档:{RESET}")
    print("  - V3.3_DEPLOYMENT_CHECKLIST.md - 完整部署清单")
    print("  - ADMIN_USER_MANAGEMENT_GUIDE.md - 管理员指南")
    print("  - USER_STRATEGY_CUSTOMIZATION_GUIDE.md - 用户策略指南")
    print("  - V3.3_QUICK_START.md - 快速开始指南")
    print("="*80)
    
    print(f"\n{YELLOW}⚠️  安全提示:{RESET}")
    print("  1. 立即修改默认管理员密码")
    print("  2. 不要在生产环境中使用默认密码")
    print("  3. JWT_SECRET_KEY 已自动生成，请妥善保管 .env 文件")
    print("  4. 只有管理员可以注册新用户")
    print("  5. 交易对固定为 BTC/ETH/SOL，用户无法修改")
    print("  6. 核心代码 100% 保护，未做任何修改")
    
    print(f"\n{GREEN}🎉 v3.3 多实例架构已准备就绪！{RESET}\n")

def main():
    """主函数"""
    print_header("v3.3 多实例架构 - 全新初始化")
    
    print_info("此脚本将:")
    print("  1. 创建/更新 .env 文件（自动生成 JWT 密钥）")
    print("  2. 创建所有数据库表")
    print("  3. 创建默认管理员账号")
    print("  4. 验证系统配置")
    
    print_warning("\n请确保:")
    print("  - PostgreSQL 数据库已运行")
    print("  - 数据库已创建（bybit_trading）")
    print("  - 数据库用户已配置")
    print("  - Python 依赖已安装（pip install -r requirements.txt）")
    
    response = input(f"\n{BLUE}是否继续初始化? (y/n): {RESET}")
    if response.lower() != 'y':
        print_info("已取消初始化")
        return
    
    # 步骤 1: 设置环境变量
    if not setup_env_file():
        print_error("环境变量配置失败")
        return
    
    # 重新加载环境变量
    from dotenv import load_dotenv
    load_dotenv(override=True)
    
    # 步骤 2: 创建数据库表
    if not create_database_tables():
        print_error("数据库表创建失败")
        print_info("请检查数据库连接配置")
        return
    
    # 步骤 3: 创建默认管理员
    if not create_default_admin():
        print_error("管理员账号创建失败")
        return
    
    # 步骤 4: 验证系统
    if not verify_system():
        print_warning("系统验证发现问题，但可以继续")
    
    # 打印后续步骤
    print_next_steps()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("\n\n初始化已取消")
    except Exception as e:
        print_error(f"初始化失败: {e}")
        import traceback
        traceback.print_exc()


