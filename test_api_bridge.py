"""
🧪 API桥接层测试脚本
═══════════════════════════════════════════════════════════════

功能：
1. 测试所有统一API端点
2. 验证前后端对接
3. 检查响应格式
4. 自动生成测试报告

使用方法：
    python test_api_bridge.py

需要：
    - 后端服务器运行在 http://localhost:8000
    - 有效的管理员账号（admin/admin123）
"""

import requests
import json
import sys
from datetime import datetime
from typing import Dict, Any, List

# ============================================================================
# 配置
# ============================================================================

API_BASE_URL = "http://localhost:8000"
USERNAME = "admin"
PASSWORD = "admin123"

# 颜色输出
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_success(msg):
    print(f"{Colors.GREEN}✅ {msg}{Colors.ENDC}")

def print_error(msg):
    print(f"{Colors.RED}❌ {msg}{Colors.ENDC}")

def print_warning(msg):
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.ENDC}")

def print_info(msg):
    print(f"{Colors.BLUE}ℹ️  {msg}{Colors.ENDC}")

def print_header(msg):
    print(f"\n{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}{msg}{Colors.ENDC}")
    print(f"{Colors.BOLD}{'='*60}{Colors.ENDC}")

# ============================================================================
# 测试类
# ============================================================================

class APIBridgeTest:
    def __init__(self):
        self.token = None
        self.results = []
        self.passed = 0
        self.failed = 0
    
    def login(self):
        """登录获取Token"""
        print_header("1. 测试登录")
        
        try:
            response = requests.post(
                f"{API_BASE_URL}/api/auth/login",
                data={
                    "username": USERNAME,
                    "password": PASSWORD
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                print_success(f"登录成功")
                print_info(f"Token: {self.token[:50]}...")
                self.add_result("登录", True)
                return True
            else:
                print_error(f"登录失败: {response.status_code}")
                print_error(response.text)
                self.add_result("登录", False)
                return False
                
        except Exception as e:
            print_error(f"登录异常: {e}")
            self.add_result("登录", False)
            return False
    
    def get_headers(self):
        """获取请求头"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def add_result(self, test_name: str, passed: bool, details: str = ""):
        """记录测试结果"""
        self.results.append({
            "test": test_name,
            "passed": passed,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })
        
        if passed:
            self.passed += 1
        else:
            self.failed += 1
    
    def test_health_check(self):
        """测试健康检查"""
        print_header("2. 测试健康检查")
        
        try:
            response = requests.get(f"{API_BASE_URL}/health")
            
            if response.status_code == 200:
                data = response.json()
                print_success("健康检查通过")
                print_info(f"状态: {data.get('status')}")
                print_info(f"版本: {data.get('version')}")
                self.add_result("健康检查", True)
            else:
                print_error(f"健康检查失败: {response.status_code}")
                self.add_result("健康检查", False)
                
        except Exception as e:
            print_error(f"健康检查异常: {e}")
            self.add_result("健康检查", False)
    
    def test_trading_status(self):
        """测试获取交易系统状态"""
        print_header("3. 测试获取交易系统状态")
        
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/trading/status",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success("获取状态成功")
                
                # 检查响应格式
                if isinstance(data, dict):
                    if 'data' in data:
                        status = data['data']
                    else:
                        status = data
                    
                    print_info(f"运行状态: {status.get('is_running')}")
                    print_info(f"运行模式: {status.get('mode')}")
                    print_info(f"总交易数: {status.get('total_trades')}")
                    self.add_result("获取状态", True)
                else:
                    print_warning("响应格式不标准")
                    self.add_result("获取状态", True, "格式待优化")
            else:
                print_error(f"获取状态失败: {response.status_code}")
                print_error(response.text)
                self.add_result("获取状态", False)
                
        except Exception as e:
            print_error(f"获取状态异常: {e}")
            self.add_result("获取状态", False)
    
    def test_get_positions(self):
        """测试获取持仓"""
        print_header("4. 测试获取持仓")
        
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/positions",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success("获取持仓成功")
                
                # 提取持仓数据
                if isinstance(data, dict) and 'data' in data:
                    positions = data['data'].get('positions', [])
                elif isinstance(data, dict) and 'positions' in data:
                    positions = data['positions']
                elif isinstance(data, list):
                    positions = data
                else:
                    positions = []
                
                print_info(f"持仓数量: {len(positions)}")
                self.add_result("获取持仓", True)
            else:
                print_error(f"获取持仓失败: {response.status_code}")
                self.add_result("获取持仓", False)
                
        except Exception as e:
            print_error(f"获取持仓异常: {e}")
            self.add_result("获取持仓", False)
    
    def test_get_trades(self):
        """测试获取交易记录"""
        print_header("5. 测试获取交易记录")
        
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/trades?limit=10",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success("获取交易记录成功")
                
                # 提取交易数据
                if isinstance(data, dict) and 'data' in data:
                    trades = data['data'].get('trades', [])
                elif isinstance(data, dict) and 'trades' in data:
                    trades = data['trades']
                elif isinstance(data, list):
                    trades = data
                else:
                    trades = []
                
                print_info(f"交易记录数: {len(trades)}")
                self.add_result("获取交易记录", True)
            else:
                print_error(f"获取交易记录失败: {response.status_code}")
                self.add_result("获取交易记录", False)
                
        except Exception as e:
            print_error(f"获取交易记录异常: {e}")
            self.add_result("获取交易记录", False)
    
    def test_get_balance(self):
        """测试获取余额"""
        print_header("6. 测试获取余额")
        
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/balance",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success("获取余额成功")
                
                # 提取余额数据
                if isinstance(data, dict) and 'data' in data:
                    balance_data = data['data']
                else:
                    balance_data = data
                
                print_info(f"余额: {balance_data.get('balance', 0)}")
                self.add_result("获取余额", True)
            else:
                print_error(f"获取余额失败: {response.status_code}")
                self.add_result("获取余额", False)
                
        except Exception as e:
            print_error(f"获取余额异常: {e}")
            self.add_result("获取余额", False)
    
    def test_get_statistics(self):
        """测试获取统计"""
        print_header("7. 测试获取统计")
        
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/statistics/summary",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success("获取统计成功")
                
                # 提取统计数据
                if isinstance(data, dict) and 'data' in data:
                    stats = data['data']
                else:
                    stats = data
                
                print_info(f"总交易数: {stats.get('total_trades', 0)}")
                print_info(f"胜率: {stats.get('win_rate', 0)}%")
                self.add_result("获取统计", True)
            else:
                print_error(f"获取统计失败: {response.status_code}")
                self.add_result("获取统计", False)
                
        except Exception as e:
            print_error(f"获取统计异常: {e}")
            self.add_result("获取统计", False)
    
    def test_start_trading(self):
        """测试启动交易系统"""
        print_header("8. 测试启动交易系统")
        print_warning("这个测试会实际启动交易系统，请确认！")
        
        try:
            response = requests.post(
                f"{API_BASE_URL}/api/trading/start?mode=demo",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success("启动请求成功")
                
                if isinstance(data, dict):
                    success = data.get('success', False)
                    message = data.get('message', '')
                    print_info(f"结果: {message}")
                    self.add_result("启动交易系统", success)
                else:
                    self.add_result("启动交易系统", True)
            else:
                print_error(f"启动失败: {response.status_code}")
                print_error(response.text)
                self.add_result("启动交易系统", False)
                
        except Exception as e:
            print_error(f"启动异常: {e}")
            self.add_result("启动交易系统", False)
    
    def test_stop_trading(self):
        """测试停止交易系统"""
        print_header("9. 测试停止交易系统")
        
        try:
            response = requests.post(
                f"{API_BASE_URL}/api/trading/stop",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success("停止请求成功")
                
                if isinstance(data, dict):
                    success = data.get('success', False)
                    message = data.get('message', '')
                    print_info(f"结果: {message}")
                    self.add_result("停止交易系统", success)
                else:
                    self.add_result("停止交易系统", True)
            else:
                print_error(f"停止失败: {response.status_code}")
                self.add_result("停止交易系统", False)
                
        except Exception as e:
            print_error(f"停止异常: {e}")
            self.add_result("停止交易系统", False)
    
    def generate_report(self):
        """生成测试报告"""
        print_header("📊 测试报告")
        
        print(f"\n总测试数: {len(self.results)}")
        print(f"{Colors.GREEN}通过: {self.passed}{Colors.ENDC}")
        print(f"{Colors.RED}失败: {self.failed}{Colors.ENDC}")
        print(f"通过率: {self.passed/len(self.results)*100:.1f}%\n")
        
        print("详细结果：")
        for i, result in enumerate(self.results, 1):
            status = f"{Colors.GREEN}✅{Colors.ENDC}" if result['passed'] else f"{Colors.RED}❌{Colors.ENDC}"
            print(f"{i}. {status} {result['test']}")
            if result['details']:
                print(f"   └─ {result['details']}")
        
        # 保存到文件
        report_file = f"api_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump({
                "summary": {
                    "total": len(self.results),
                    "passed": self.passed,
                    "failed": self.failed,
                    "pass_rate": f"{self.passed/len(self.results)*100:.1f}%"
                },
                "results": self.results
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 详细报告已保存到: {report_file}")
        
        return self.failed == 0
    
    def run_all_tests(self):
        """运行所有测试"""
        print(f"\n{Colors.BOLD}{'='*80}{Colors.ENDC}")
        print(f"{Colors.BOLD}{'🧪 API桥接层测试套件':^80}{Colors.ENDC}")
        print(f"{Colors.BOLD}{'='*80}{Colors.ENDC}")
        
        # 登录
        if not self.login():
            print_error("登录失败，无法继续测试")
            return False
        
        # 运行测试
        self.test_health_check()
        self.test_trading_status()
        self.test_get_positions()
        self.test_get_trades()
        self.test_get_balance()
        self.test_get_statistics()
        
        # 可选：测试启动/停止（可能影响生产环境）
        # self.test_start_trading()
        # self.test_stop_trading()
        
        # 生成报告
        success = self.generate_report()
        
        if success:
            print(f"\n{Colors.GREEN}{'='*80}{Colors.ENDC}")
            print(f"{Colors.GREEN}{Colors.BOLD}{'🎉 所有测试通过！':^80}{Colors.ENDC}")
            print(f"{Colors.GREEN}{'='*80}{Colors.ENDC}\n")
        else:
            print(f"\n{Colors.RED}{'='*80}{Colors.ENDC}")
            print(f"{Colors.RED}{Colors.BOLD}{'❌ 部分测试失败，请检查':^80}{Colors.ENDC}")
            print(f"{Colors.RED}{'='*80}{Colors.ENDC}\n")
        
        return success

# ============================================================================
# 主函数
# ============================================================================

def main():
    """主函数"""
    test = APIBridgeTest()
    success = test.run_all_tests()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

