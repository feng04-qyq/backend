"""
Bybit API 配置向导
帮助用户快速配置测试网或主网API密钥
"""

import json
import os
import sys

def print_header():
    print("\n" + "="*80)
    print("  Bybit API 配置向导")
    print("="*80 + "\n")

def print_section(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")

def choose_network():
    """选择网络环境"""
    print_section("步骤 1/3：选择网络环境")
    
    print("请选择要配置的网络环境：")
    print("\n  [1] 测试网 (Testnet) - 推荐新手和策略测试")
    print("      - 网址: https://testnet.bybit.com")
    print("      - API: https://api-testnet.bybit.com")
    print("      - 特点: 免费、无风险、10,000 USDT测试币")
    print("\n  [2] 主网 (Mainnet) - 用于实盘交易")
    print("      - 网址: https://www.bybit.com")
    print("      - API: https://api.bybit.com")
    print("      - 特点: 真实资金、有风险")
    
    while True:
        choice = input("\n请输入选项 (1 或 2): ").strip()
        if choice == "1":
            return True, "testnet"
        elif choice == "2":
            confirm = input("\n[警告] 您选择了主网（实盘）。确认继续？(yes/no): ").strip().lower()
            if confirm == "yes":
                return False, "mainnet"
            else:
                print("已取消，请重新选择。")
        else:
            print("无效选项，请输入 1 或 2")

def get_api_credentials(network_name):
    """获取API密钥"""
    print_section("步骤 2/3：输入API密钥")
    
    if network_name == "testnet":
        print("测试网API密钥获取方式：")
        print("  1. 访问: https://testnet.bybit.com/")
        print("  2. 注册/登录账号")
        print("  3. 进入 [账户] -> [API管理]")
        print("  4. 创建新密钥，启用权限：")
        print("     [√] 读取 (Read)")
        print("     [√] 交易 (Trade)")
        print("     [ ] 提现 (Withdraw) - 不要启用")
    else:
        print("主网API密钥获取方式：")
        print("  1. 访问: https://www.bybit.com/")
        print("  2. 登录账号")
        print("  3. 进入 [账户] -> [API管理]")
        print("  4. 创建新密钥，启用权限：")
        print("     [√] 读取 (Read)")
        print("     [√] 交易 (Trade)")
        print("     [ ] 提现 (Withdraw) - 强烈建议不要启用")
    
    print(f"\n[提示] 如果还没有API密钥，请先访问上述网站创建")
    print("[提示] API Secret只显示一次，请妥善保存\n")
    
    api_key = input("请输入API Key: ").strip()
    api_secret = input("请输入API Secret: ").strip()
    
    if not api_key or not api_secret:
        print("\n[错误] API密钥不能为空")
        sys.exit(1)
    
    return api_key, api_secret

def configure_trading_params():
    """配置交易参数"""
    print_section("步骤 3/3：配置交易参数（可选）")
    
    print("是否使用默认交易参数？")
    print("\n默认参数：")
    print("  - 杠杆: 10x")
    print("  - 最大仓位: 30%")
    print("  - 交易间隔: 60秒")
    print("  - 最小余额: 10 USDT")
    
    use_default = input("\n使用默认参数？(yes/no，默认yes): ").strip().lower()
    
    if use_default == "no":
        try:
            leverage = int(input("  杠杆倍数 (1-15，推荐10): ").strip() or "10")
            max_position = float(input("  最大仓位比例 (0.05-0.30，推荐0.30): ").strip() or "0.30")
            interval = int(input("  交易间隔秒数 (60-600，推荐60): ").strip() or "60")
            min_balance = float(input("  最小余额 USDT (10-100，推荐10): ").strip() or "10")
            
            return {
                "leverage": max(1, min(15, leverage)),
                "max_position": max(0.05, min(0.30, max_position)),
                "interval": max(60, min(600, interval)),
                "min_balance": max(10, min(100, min_balance))
            }
        except ValueError:
            print("\n[警告] 输入无效，使用默认参数")
    
    return {
        "leverage": 10,
        "max_position": 0.30,
        "interval": 60,
        "min_balance": 10.0
    }

def save_config(use_testnet, api_key, api_secret, params):
    """保存配置文件"""
    config = {
        "_comment": "Bybit实盘交易系统配置文件",
        "_warning": "⚠️ 请妥善保管API密钥，不要泄露给他人",
        
        "bybit_api_key": api_key,
        "bybit_api_secret": api_secret,
        
        "_testnet_info": "建议先使用测试网进行充分测试",
        "use_testnet": use_testnet,
        
        "_symbols_info": "监控和交易的资产列表",
        "symbols": [
            "BTCUSDT_PERPETUAL",
            "ETHUSDT_PERPETUAL",
            "SOLUSDT_PERPETUAL"
        ],
        
        "_deepseek_config_info": "DeepSeek AI配置文件路径",
        "deepseek_config": "deepseek_config.json",
        
        "_leverage_info": "默认杠杆（AI可选1-15倍）",
        "default_leverage": params["leverage"],
        
        "_trading_interval_info": "交易决策间隔（秒），建议60-300秒",
        "trading_interval": params["interval"],
        
        "_max_position_pct_info": "最大仓位比例（0.0-0.3，即0-30%）",
        "max_position_pct": params["max_position"],
        
        "_min_balance_info": "最小余额保护（USDT）",
        "min_balance": params["min_balance"],
        
        "_risk_control": {
            "description": "风险控制参数",
            "max_position": f"{params['max_position']*100:.0f}%",
            "stop_loss": "AI自主决策",
            "extreme_protection": "已启用（5种机制）"
        }
    }
    
    config_file = "live_trading_config.json"
    
    # 备份旧配置
    if os.path.exists(config_file):
        backup_file = "live_trading_config.json.backup"
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                old_config = f.read()
            with open(backup_file, 'w', encoding='utf-8') as f:
                f.write(old_config)
            print(f"\n[提示] 旧配置已备份到: {backup_file}")
        except:
            pass
    
    # 保存新配置
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    return config_file

def main():
    print_header()
    
    print("欢迎使用Bybit API配置向导！")
    print("本向导将帮助您快速配置交易系统。\n")
    
    # 步骤1：选择网络
    use_testnet, network_name = choose_network()
    
    # 步骤2：获取API密钥
    api_key, api_secret = get_api_credentials(network_name)
    
    # 步骤3：配置参数
    params = configure_trading_params()
    
    # 保存配置
    print_section("保存配置")
    config_file = save_config(use_testnet, api_key, api_secret, params)
    
    print(f"[成功] 配置已保存到: {config_file}")
    print(f"\n配置摘要：")
    print(f"  网络环境: {'测试网 (Testnet)' if use_testnet else '主网 (Mainnet)'}")
    print(f"  API密钥: {api_key[:10]}...{api_key[-5:]}")
    print(f"  默认杠杆: {params['leverage']}x")
    print(f"  最大仓位: {params['max_position']*100:.0f}%")
    print(f"  交易间隔: {params['interval']}秒")
    print(f"  最小余额: {params['min_balance']} USDT")
    
    # 下一步提示
    print_section("下一步")
    
    print("配置完成！接下来：")
    print("\n1. 运行API测试（验证配置是否正确）：")
    print("   python test_bybit_api_simple.py")
    
    print("\n2. 如果测试通过，启动交易系统：")
    print("   python bybit_live_trading_system.py")
    
    if use_testnet:
        print("\n[提示] 您正在使用测试网，可以安全地测试策略")
        print("       测试网账户通常会自动获得10,000 USDT测试币")
    else:
        print("\n[警告] 您正在使用主网（实盘）！")
        print("       - 建议先在测试网充分测试")
        print("       - 使用小额资金试运行")
        print("       - 密切监控系统状态")
        print("       - 设置合理的止损")
    
    print("\n" + "="*80 + "\n")
    
    # 询问是否立即测试
    test_now = input("是否现在运行API测试？(yes/no): ").strip().lower()
    if test_now == "yes":
        print("\n启动API测试...\n")
        os.system("python test_bybit_api_simple.py")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[取消] 配置已取消")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n[错误] 配置过程发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


