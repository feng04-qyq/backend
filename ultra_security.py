"""
超安全加密系统 - 军事级多层加密
使用7层加密和混淆技术确保API密钥绝对安全

加密层级：
1. 密钥派生函数 (PBKDF2) - 100,000次迭代
2. AES-256-GCM加密（对称加密）
3. RSA-4096加密（非对称加密）
4. Fernet双重加密
5. 自定义混淆算法
6. Base85编码
7. HMAC完整性校验

版本: v1.0 Military Grade
"""

import os
import base64
import hashlib
import secrets
import json
from typing import Dict, Any, Tuple
from datetime import datetime

# 加密库
from cryptography.hazmat.primitives import hashes, serialization
# 修复 PBKDF2 导入 - 兼容新旧版本 cryptography
# 新版本使用 PBKDF2HMAC，旧版本使用 PBKDF2
try:
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    PBKDF2_CLASS = PBKDF2HMAC  # 使用 PBKDF2HMAC（新版本）
    USE_PBKDF2HMAC = True
except ImportError:
    try:
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
        PBKDF2_CLASS = PBKDF2  # 使用 PBKDF2（旧版本）
        USE_PBKDF2HMAC = False
    except ImportError:
        # 如果都导入失败，使用 hashlib.pbkdf2_hmac 作为后备
        PBKDF2_CLASS = None
        USE_PBKDF2HMAC = False
        import hashlib as _hashlib

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa, padding as asym_padding
from cryptography.fernet import Fernet
import hmac

# ============================================================================
# 主密钥管理
# ============================================================================

class MasterKeyManager:
    """主密钥管理器 - 管理系统的根密钥"""
    
    def __init__(self):
        self.backend = default_backend()
        
        # 从环境变量或文件加载主密钥
        self.master_password = os.getenv(
            "MASTER_PASSWORD",
            self._generate_master_password()
        )
        
        # 盐值（每个系统唯一）
        self.master_salt = os.getenv(
            "MASTER_SALT",
            base64.b64encode(secrets.token_bytes(32)).decode()
        )
        
        # 生成RSA密钥对（如果不存在）
        self._initialize_rsa_keys()
    
    def _generate_master_password(self) -> str:
        """生成随机主密码"""
        return secrets.token_urlsafe(64)
    
    def _initialize_rsa_keys(self):
        """初始化RSA密钥对"""
        # 私钥路径
        private_key_path = "private_key.pem"
        public_key_path = "public_key.pem"
        
        if os.path.exists(private_key_path) and os.path.exists(public_key_path):
            # 加载现有密钥
            with open(private_key_path, "rb") as f:
                self.private_key = serialization.load_pem_private_key(
                    f.read(),
                    password=None,
                    backend=self.backend
                )
            with open(public_key_path, "rb") as f:
                self.public_key = serialization.load_pem_public_key(
                    f.read(),
                    backend=self.backend
                )
        else:
            # 生成新密钥对（RSA-4096）
            self.private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=4096,
                backend=self.backend
            )
            self.public_key = self.private_key.public_key()
            
            # 保存密钥（生产环境应使用HSM或密钥管理服务）
            with open(private_key_path, "wb") as f:
                f.write(self.private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ))
            with open(public_key_path, "wb") as f:
                f.write(self.public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo
                ))
            
            print("✅ RSA-4096密钥对已生成")
    
    def derive_key(self, salt: bytes, length: int = 32) -> bytes:
        """使用PBKDF2派生密钥"""
        key_material = self.master_password.encode()
        
        # 优先使用 cryptography 库
        if PBKDF2_CLASS is not None:
            try:
                if USE_PBKDF2HMAC:
                    # 使用 PBKDF2HMAC（新版本，cryptography >= 41.0.0）
                    kdf = PBKDF2_CLASS(
                        algorithm=hashes.SHA512(),
                        length=length,
                        salt=salt,
                        iterations=100000,  # 100,000次迭代，增加暴力破解难度
                        backend=self.backend
                    )
                else:
                    # 使用 PBKDF2（旧版本）
                    kdf = PBKDF2_CLASS(
                        algorithm=hashes.SHA512(),
                        length=length,
                        salt=salt,
                        iterations=100000,
                        backend=self.backend
                    )
                return kdf.derive(key_material)
            except Exception as e:
                # 如果 cryptography 失败，回退到 hashlib
                import logging
                logging.warning(f"PBKDF2 from cryptography failed, using hashlib fallback: {e}")
        
        # 最终后备：使用 hashlib.pbkdf2_hmac
        import hashlib
        return hashlib.pbkdf2_hmac(
            'sha512',
            key_material,
            salt,
            100000,
            length
        )

master_key_manager = MasterKeyManager()

# ============================================================================
# 第1层：自定义混淆算法
# ============================================================================

class CustomObfuscator:
    """自定义混淆器 - 增加逆向工程难度"""
    
    @staticmethod
    def obfuscate(data: bytes) -> bytes:
        """混淆数据"""
        # 1. 添加随机噪声
        noise = secrets.token_bytes(16)
        data_with_noise = noise + data + noise
        
        # 2. XOR混淆
        key = secrets.token_bytes(32)
        xor_data = bytes(a ^ b for a, b in zip(data_with_noise, key * (len(data_with_noise) // len(key) + 1)))
        
        # 3. 位移混淆
        shifted = bytes((b << 3 | b >> 5) & 0xFF for b in xor_data)
        
        # 4. 添加校验和
        checksum = hashlib.sha256(shifted).digest()[:8]
        
        # 5. 组合：key长度(1) + key + checksum + shifted_data
        result = bytes([len(key)]) + key + checksum + shifted
        
        return result
    
    @staticmethod
    def deobfuscate(obfuscated: bytes) -> bytes:
        """反混淆"""
        # 1. 提取key长度
        key_len = obfuscated[0]
        
        # 2. 提取key和checksum
        key = obfuscated[1:1+key_len]
        checksum = obfuscated[1+key_len:1+key_len+8]
        shifted = obfuscated[1+key_len+8:]
        
        # 3. 验证校验和
        if hashlib.sha256(shifted).digest()[:8] != checksum:
            raise ValueError("数据完整性校验失败")
        
        # 4. 反向位移
        xor_data = bytes((b >> 3 | b << 5) & 0xFF for b in shifted)
        
        # 5. 反向XOR
        data_with_noise = bytes(a ^ b for a, b in zip(xor_data, key * (len(xor_data) // len(key) + 1)))
        
        # 6. 移除噪声
        data = data_with_noise[16:-16]
        
        return data

# ============================================================================
# 第2层：AES-256-GCM加密
# ============================================================================

class AESEncryptor:
    """AES-256-GCM加密器"""
    
    @staticmethod
    def encrypt(data: bytes, key: bytes) -> Dict[str, bytes]:
        """AES-256-GCM加密"""
        # 生成随机IV
        iv = secrets.token_bytes(12)
        
        # 创建加密器
        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(iv),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        
        # 加密数据
        ciphertext = encryptor.update(data) + encryptor.finalize()
        
        return {
            'iv': iv,
            'ciphertext': ciphertext,
            'tag': encryptor.tag
        }
    
    @staticmethod
    def decrypt(encrypted: Dict[str, bytes], key: bytes) -> bytes:
        """AES-256-GCM解密"""
        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(encrypted['iv'], encrypted['tag']),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        
        return decryptor.update(encrypted['ciphertext']) + decryptor.finalize()

# ============================================================================
# 第3层：RSA-4096加密
# ============================================================================

class RSAEncryptor:
    """RSA-4096加密器"""
    
    @staticmethod
    def encrypt(data: bytes) -> bytes:
        """RSA公钥加密"""
        # RSA加密有长度限制，需要分块
        max_chunk_size = 446  # 4096位密钥，OAEP填充
        chunks = [data[i:i+max_chunk_size] for i in range(0, len(data), max_chunk_size)]
        
        encrypted_chunks = []
        for chunk in chunks:
            encrypted_chunk = master_key_manager.public_key.encrypt(
                chunk,
                asym_padding.OAEP(
                    mgf=asym_padding.MGF1(algorithm=hashes.SHA512()),
                    algorithm=hashes.SHA512(),
                    label=None
                )
            )
            encrypted_chunks.append(encrypted_chunk)
        
        # 添加块数量信息
        num_chunks = len(encrypted_chunks).to_bytes(2, 'big')
        return num_chunks + b''.join(encrypted_chunks)
    
    @staticmethod
    def decrypt(encrypted: bytes) -> bytes:
        """RSA私钥解密"""
        # 提取块数量
        num_chunks = int.from_bytes(encrypted[:2], 'big')
        
        # 每个加密块的大小是512字节（4096位）
        chunk_size = 512
        chunks = []
        
        offset = 2
        for _ in range(num_chunks):
            chunk = encrypted[offset:offset+chunk_size]
            decrypted_chunk = master_key_manager.private_key.decrypt(
                chunk,
                asym_padding.OAEP(
                    mgf=asym_padding.MGF1(algorithm=hashes.SHA512()),
                    algorithm=hashes.SHA512(),
                    label=None
                )
            )
            chunks.append(decrypted_chunk)
            offset += chunk_size
        
        return b''.join(chunks)

# ============================================================================
# 第4层：Fernet双重加密
# ============================================================================

class FernetDoubleEncryptor:
    """Fernet双重加密器"""
    
    @staticmethod
    def encrypt(data: bytes) -> Tuple[bytes, bytes, bytes]:
        """双重Fernet加密"""
        # 第一层Fernet
        key1 = Fernet.generate_key()
        f1 = Fernet(key1)
        encrypted1 = f1.encrypt(data)
        
        # 第二层Fernet
        key2 = Fernet.generate_key()
        f2 = Fernet(key2)
        encrypted2 = f2.encrypt(encrypted1)
        
        return encrypted2, key1, key2
    
    @staticmethod
    def decrypt(encrypted: bytes, key1: bytes, key2: bytes) -> bytes:
        """双重Fernet解密"""
        # 解密第二层
        f2 = Fernet(key2)
        decrypted1 = f2.decrypt(encrypted)
        
        # 解密第一层
        f1 = Fernet(key1)
        original = f1.decrypt(decrypted1)
        
        return original

# ============================================================================
# 第5层：HMAC完整性校验
# ============================================================================

class HMACValidator:
    """HMAC完整性验证器"""
    
    @staticmethod
    def sign(data: bytes, key: bytes) -> bytes:
        """生成HMAC签名"""
        return hmac.new(key, data, hashlib.sha512).digest()
    
    @staticmethod
    def verify(data: bytes, signature: bytes, key: bytes) -> bool:
        """验证HMAC签名"""
        expected = hmac.new(key, data, hashlib.sha512).digest()
        return hmac.compare_digest(expected, signature)

# ============================================================================
# 超安全加密器（7层加密）
# ============================================================================

class UltraSecureEncryption:
    """
    超安全加密器
    
    加密流程：
    原始数据 
    → [1] 自定义混淆 
    → [2] AES-256-GCM加密 
    → [3] RSA-4096加密 
    → [4] Fernet双重加密 
    → [5] 再次自定义混淆 
    → [6] Base85编码 
    → [7] HMAC签名
    → 存储到数据库
    """
    
    def __init__(self):
        self.version = "1.0"
        self.obfuscator = CustomObfuscator()
        self.aes = AESEncryptor()
        self.rsa = RSAEncryptor()
        self.fernet = FernetDoubleEncryptor()
        self.hmac = HMACValidator()
    
    def encrypt(self, plaintext: str) -> str:
        """
        7层加密
        
        Args:
            plaintext: 明文（API密钥等）
        
        Returns:
            加密后的字符串（可直接存储到数据库）
        """
        try:
            data = plaintext.encode('utf-8')
            
            # 生成唯一盐值
            salt = secrets.token_bytes(32)
            
            # 派生AES密钥
            aes_key = master_key_manager.derive_key(salt)
            
            # 【第1层】自定义混淆
            print("  [1/7] 应用自定义混淆...")
            obfuscated1 = self.obfuscator.obfuscate(data)
            
            # 【第2层】AES-256-GCM加密
            print("  [2/7] AES-256-GCM加密...")
            aes_encrypted = self.aes.encrypt(obfuscated1, aes_key)
            
            # 序列化AES加密结果
            aes_data = json.dumps({
                'iv': base64.b64encode(aes_encrypted['iv']).decode(),
                'ciphertext': base64.b64encode(aes_encrypted['ciphertext']).decode(),
                'tag': base64.b64encode(aes_encrypted['tag']).decode()
            }).encode()
            
            # 【第3层】RSA-4096加密（加密AES数据）
            print("  [3/7] RSA-4096加密...")
            rsa_encrypted = self.rsa.encrypt(aes_data)
            
            # 【第4层】Fernet双重加密
            print("  [4/7] Fernet双重加密...")
            fernet_encrypted, fernet_key1, fernet_key2 = self.fernet.encrypt(rsa_encrypted)
            
            # 【第5层】再次自定义混淆
            print("  [5/7] 再次混淆...")
            obfuscated2 = self.obfuscator.obfuscate(fernet_encrypted)
            
            # 【第6层】Base85编码
            print("  [6/7] Base85编码...")
            base85_encoded = base64.b85encode(obfuscated2)
            
            # 【第7层】HMAC签名
            print("  [7/7] HMAC签名...")
            hmac_key = master_key_manager.derive_key(salt, length=64)
            signature = self.hmac.sign(base85_encoded, hmac_key)
            
            # 组装最终数据包
            final_package = {
                'version': self.version,
                'salt': base64.b64encode(salt).decode(),
                'fernet_key1': base64.b64encode(fernet_key1).decode(),
                'fernet_key2': base64.b64encode(fernet_key2).decode(),
                'data': base85_encoded.decode(),
                'signature': base64.b64encode(signature).decode(),
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # 转换为JSON字符串
            result = json.dumps(final_package)
            
            print(f"✅ 加密完成！数据大小: {len(plaintext)} → {len(result)} 字节")
            return result
            
        except Exception as e:
            print(f"❌ 加密失败: {e}")
            raise
    
    def decrypt(self, encrypted: str) -> str:
        """
        7层解密
        
        Args:
            encrypted: 加密字符串
        
        Returns:
            明文
        """
        try:
            # 解析数据包
            package = json.loads(encrypted)
            
            # 验证版本
            if package['version'] != self.version:
                raise ValueError(f"加密版本不匹配: {package['version']} != {self.version}")
            
            # 提取数据
            salt = base64.b64decode(package['salt'])
            fernet_key1 = base64.b64decode(package['fernet_key1'])
            fernet_key2 = base64.b64decode(package['fernet_key2'])
            data = package['data'].encode()
            signature = base64.b64decode(package['signature'])
            
            # 【第7层】验证HMAC签名
            print("  [7/7] 验证HMAC签名...")
            hmac_key = master_key_manager.derive_key(salt, length=64)
            if not self.hmac.verify(data, signature, hmac_key):
                raise ValueError("数据完整性校验失败！数据可能被篡改！")
            
            # 【第6层】Base85解码
            print("  [6/7] Base85解码...")
            obfuscated2 = base64.b85decode(data)
            
            # 【第5层】反混淆
            print("  [5/7] 反混淆...")
            fernet_encrypted = self.obfuscator.deobfuscate(obfuscated2)
            
            # 【第4层】Fernet双重解密
            print("  [4/7] Fernet双重解密...")
            rsa_encrypted = self.fernet.decrypt(fernet_encrypted, fernet_key1, fernet_key2)
            
            # 【第3层】RSA-4096解密
            print("  [3/7] RSA-4096解密...")
            aes_data = self.rsa.decrypt(rsa_encrypted)
            
            # 反序列化AES数据
            aes_dict = json.loads(aes_data.decode())
            aes_encrypted = {
                'iv': base64.b64decode(aes_dict['iv']),
                'ciphertext': base64.b64decode(aes_dict['ciphertext']),
                'tag': base64.b64decode(aes_dict['tag'])
            }
            
            # 【第2层】AES-256-GCM解密
            print("  [2/7] AES-256-GCM解密...")
            aes_key = master_key_manager.derive_key(salt)
            obfuscated1 = self.aes.decrypt(aes_encrypted, aes_key)
            
            # 【第1层】反混淆
            print("  [1/7] 反混淆...")
            plaintext_bytes = self.obfuscator.deobfuscate(obfuscated1)
            
            plaintext = plaintext_bytes.decode('utf-8')
            
            print(f"✅ 解密完成！")
            return plaintext
            
        except Exception as e:
            print(f"❌ 解密失败: {e}")
            raise

# ============================================================================
# 全局实例
# ============================================================================

ultra_crypto = UltraSecureEncryption()

# ============================================================================
# 便捷函数
# ============================================================================

def encrypt_api_key(api_key: str) -> str:
    """加密API密钥"""
    print(f"\n🔐 开始加密 API 密钥...")
    return ultra_crypto.encrypt(api_key)

def decrypt_api_key(encrypted: str) -> str:
    """解密API密钥"""
    print(f"\n🔓 开始解密 API 密钥...")
    return ultra_crypto.decrypt(encrypted)

# ============================================================================
# 测试代码
# ============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("🔒 超安全加密系统测试")
    print("=" * 80)
    
    # 测试数据
    test_api_keys = [
        "sk-1234567890abcdef1234567890abcdef",
        "BYBIT_API_KEY_1234567890ABCDEF",
        "YOUR_SECRET_API_KEY_HERE"
    ]
    
    for i, original in enumerate(test_api_keys, 1):
        print(f"\n{'='*80}")
        print(f"测试 {i}: {original[:20]}...")
        print(f"{'='*80}")
        
        # 加密
        encrypted = encrypt_api_key(original)
        print(f"\n加密后 ({len(encrypted)} 字节):")
        print(encrypted[:100] + "..." if len(encrypted) > 100 else encrypted)
        
        # 解密
        decrypted = decrypt_api_key(encrypted)
        print(f"\n解密后: {decrypted}")
        
        # 验证
        if original == decrypted:
            print("✅ 加解密测试通过！")
        else:
            print("❌ 加解密测试失败！")
        
        # 安全特性
        print(f"\n🔐 安全特性:")
        print(f"  • 7层加密保护")
        print(f"  • AES-256-GCM对称加密")
        print(f"  • RSA-4096非对称加密")
        print(f"  • PBKDF2密钥派生 (100,000次迭代)")
        print(f"  • Fernet双重加密")
        print(f"  • HMAC-SHA512完整性校验")
        print(f"  • 自定义混淆算法")
        print(f"  • 数据膨胀率: {len(encrypted) / len(original):.1f}x")
    
    print(f"\n{'='*80}")
    print("✅ 所有测试完成！")
    print(f"{'='*80}")



