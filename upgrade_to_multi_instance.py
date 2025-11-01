#!/usr/bin/env python3
"""
多实例架构升级脚本
快速将共享模式升级到多用户独立模式

使用方法:
    python upgrade_to_multi_instance.py

功能:
    1. 检查环境和依赖
    2. 备份数据库
    3. 执行数据库迁移
    4. 更新配置文件
    5. 验证升级结果
"""

import os
import sys
import subprocess
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
    print("\n" + "="*60)
    print(f"{BLUE}{text}{RESET}")
    print("="*60)

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

def check_files():
    """检查必需文件是否存在"""
    print_header("第 1 步: 检查文件")
    
    required_files = [
        "trading_system_multi_user_manager.py",
        "trading_api_multi_user.py",
        "MULTI_INSTANCE_IMPLEMENTATION_GUIDE.md",
    ]
    
    all_exist = True
    for file in required_files:
        if os.path.exists(file):
            print_success(f"找到文件: {file}")
        else:
            print_error(f"缺少文件: {file}")
            all_exist = False
    
    if not all_exist:
        print_error("请确保所有必需文件都已创建")
        return False
    
    return True

def backup_database():
    """备份数据库"""
    print_header("第 2 步: 备份数据库")
    
    # 读取数据库配置
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print_warning("未找到 DATABASE_URL 环境变量")
        print_info("请手动备份数据库")
        response = input("是否已完成数据库备份? (y/n): ")
        return response.lower() == 'y'
    
    # 生成备份文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"backup_v3.2_{timestamp}.sql"
    
    print_info(f"备份文件: {backup_file}")
    
    try:
        # 解析数据库 URL
        # postgresql://user:password@host:port/dbname
        import re
        match = re.match(r'postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', db_url)
        if match:
            user, password, host, port, dbname = match.groups()
            
            # 使用 pg_dump 备份
            cmd = f"pg_dump -h {host} -U {user} -d {dbname} > {backup_file}"
            print_info(f"执行命令: pg_dump -h {host} -U {user} -d {dbname}")
            
            # 设置密码环境变量
            env = os.environ.copy()
            env['PGPASSWORD'] = password
            
            result = subprocess.run(
                ["pg_dump", "-h", host, "-U", user, "-d", dbname, "-f", backup_file],
                env=env,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print_success(f"数据库已备份到: {backup_file}")
                return True
            else:
                print_error(f"备份失败: {result.stderr}")
                return False
        else:
            print_error("无法解析 DATABASE_URL")
            return False
    
    except Exception as e:
        print_error(f"备份失败: {e}")
        print_info("请手动备份数据库")
        response = input("是否已完成手动备份? (y/n): ")
        return response.lower() == 'y'

def create_migration_sql():
    """创建数据库迁移 SQL"""
    print_header("第 3 步: 创建迁移脚本")
    
    migration_sql = """-- 多实例架构数据库迁移脚本
-- 版本: v3.2 → v3.3
-- 日期: {timestamp}

BEGIN;

-- 1. 添加 user_id 字段
ALTER TABLE trades ADD COLUMN IF NOT EXISTS user_id INTEGER;
ALTER TABLE ai_decisions ADD COLUMN IF NOT EXISTS user_id INTEGER;
ALTER TABLE risk_metrics ADD COLUMN IF NOT EXISTS user_id INTEGER;
ALTER TABLE account_snapshots ADD COLUMN IF NOT EXISTS user_id INTEGER;

-- 2. 添加外键约束
ALTER TABLE trades ADD CONSTRAINT IF NOT EXISTS fk_trades_user 
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE ai_decisions ADD CONSTRAINT IF NOT EXISTS fk_ai_decisions_user 
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE risk_metrics ADD CONSTRAINT IF NOT EXISTS fk_risk_metrics_user 
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE account_snapshots ADD CONSTRAINT IF NOT EXISTS fk_account_snapshots_user 
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- 3. 添加索引
CREATE INDEX IF NOT EXISTS idx_trades_user_id ON trades(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_decisions_user_id ON ai_decisions(user_id);
CREATE INDEX IF NOT EXISTS idx_risk_metrics_user_id ON risk_metrics(user_id);
CREATE INDEX IF NOT EXISTS idx_account_snapshots_user_id ON account_snapshots(user_id);

-- 4. 迁移现有数据到管理员账户
UPDATE trades SET user_id = (SELECT id FROM users WHERE is_admin = true ORDER BY id LIMIT 1) 
WHERE user_id IS NULL;

UPDATE ai_decisions SET user_id = (SELECT id FROM users WHERE is_admin = true ORDER BY id LIMIT 1) 
WHERE user_id IS NULL;

UPDATE risk_metrics SET user_id = (SELECT id FROM users WHERE is_admin = true ORDER BY id LIMIT 1) 
WHERE user_id IS NULL;

UPDATE account_snapshots SET user_id = (SELECT id FROM users WHERE is_admin = true ORDER BY id LIMIT 1) 
WHERE user_id IS NULL;

COMMIT;

-- 验证
SELECT 
    'trades' as table_name,
    COUNT(*) as total_records,
    COUNT(user_id) as records_with_user_id
FROM trades
UNION ALL
SELECT 
    'ai_decisions',
    COUNT(*),
    COUNT(user_id)
FROM ai_decisions
UNION ALL
SELECT 
    'risk_metrics',
    COUNT(*),
    COUNT(user_id)
FROM risk_metrics;
""".format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    migration_file = "migration_v3.3.sql"
    
    with open(migration_file, 'w', encoding='utf-8') as f:
        f.write(migration_sql)
    
    print_success(f"迁移脚本已创建: {migration_file}")
    return migration_file

def run_migration(migration_file):
    """执行数据库迁移"""
    print_header("第 4 步: 执行数据库迁移")
    
    print_warning("即将执行数据库迁移，这将修改数据库结构")
    print_info("请确保已完成数据库备份")
    
    response = input("是否继续执行迁移? (y/n): ")
    if response.lower() != 'y':
        print_warning("已取消迁移")
        return False
    
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print_error("未找到 DATABASE_URL 环境变量")
        print_info(f"请手动执行: psql -f {migration_file}")
        return False
    
    try:
        import re
        match = re.match(r'postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', db_url)
        if match:
            user, password, host, port, dbname = match.groups()
            
            # 设置密码环境变量
            env = os.environ.copy()
            env['PGPASSWORD'] = password
            
            result = subprocess.run(
                ["psql", "-h", host, "-U", user, "-d", dbname, "-f", migration_file],
                env=env,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print_success("数据库迁移成功")
                print_info("输出:")
                print(result.stdout)
                return True
            else:
                print_error(f"迁移失败: {result.stderr}")
                return False
        else:
            print_error("无法解析 DATABASE_URL")
            return False
    
    except Exception as e:
        print_error(f"迁移失败: {e}")
        print_info(f"请手动执行: psql -f {migration_file}")
        return False

def update_api_server():
    """更新 API 服务器配置"""
    print_header("第 5 步: 更新 API 服务器")
    
    print_info("需要在 api_server_unified.py 中添加多用户路由")
    print_info("请手动添加以下代码:")
    
    code = """
# 在文件顶部添加导入
from trading_api_multi_user import router as multi_user_trading_router

# 在路由注册部分添加
app.include_router(
    multi_user_trading_router,
    tags=["多用户交易系统"]
)
"""
    
    print(f"{YELLOW}{code}{RESET}")
    
    response = input("是否已更新 API 服务器代码? (y/n): ")
    return response.lower() == 'y'

def verify_upgrade():
    """验证升级结果"""
    print_header("第 6 步: 验证升级")
    
    print_info("执行验证检查...")
    
    # 检查新文件
    checks = []
    
    if os.path.exists("trading_system_multi_user_manager.py"):
        checks.append(("多用户管理器文件", True))
    else:
        checks.append(("多用户管理器文件", False))
    
    if os.path.exists("trading_api_multi_user.py"):
        checks.append(("多用户 API 文件", True))
    else:
        checks.append(("多用户 API 文件", False))
    
    if os.path.exists("migration_v3.3.sql"):
        checks.append(("数据库迁移脚本", True))
    else:
        checks.append(("数据库迁移脚本", False))
    
    print("\n验证结果:")
    all_passed = True
    for check_name, passed in checks:
        if passed:
            print_success(check_name)
        else:
            print_error(check_name)
            all_passed = False
    
    return all_passed

def main():
    """主函数"""
    print_header("多实例架构升级工具 v3.3")
    
    print_info("此脚本将帮助您升级到多用户独立交易系统架构")
    print_warning("升级过程将修改数据库结构，请确保已做好备份")
    
    response = input("\n是否继续? (y/n): ")
    if response.lower() != 'y':
        print_info("已取消升级")
        return
    
    # 步骤 1: 检查文件
    if not check_files():
        print_error("升级失败: 缺少必需文件")
        return
    
    # 步骤 2: 备份数据库
    if not backup_database():
        print_error("升级失败: 数据库备份失败")
        return
    
    # 步骤 3: 创建迁移脚本
    migration_file = create_migration_sql()
    
    # 步骤 4: 执行迁移
    if not run_migration(migration_file):
        print_error("升级失败: 数据库迁移失败")
        return
    
    # 步骤 5: 更新 API 服务器
    if not update_api_server():
        print_warning("请手动更新 API 服务器代码")
    
    # 步骤 6: 验证
    if verify_upgrade():
        print_header("升级完成！")
        print_success("多实例架构已成功部署")
        print_info("\n下一步:")
        print("  1. 重启 API 服务器")
        print("  2. 更新前端代码")
        print("  3. 测试多用户功能")
        print("\n详细文档: MULTI_INSTANCE_IMPLEMENTATION_GUIDE.md")
    else:
        print_error("验证失败，请检查日志")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("\n\n升级已取消")
    except Exception as e:
        print_error(f"升级失败: {e}")
        import traceback
        traceback.print_exc()

