"""
API认证模块 - JWT Token认证
增强安全性，防止未授权访问

版本: v2.0 - 使用真实数据库
"""

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from jose import jwt, JWTError
from datetime import datetime, timedelta
import secrets
import hashlib
import os
from typing import Optional
from dotenv import load_dotenv
from sqlalchemy.orm import Session

# 导入数据库模型
from database_models import get_db, User as DBUser

# 加载环境变量
load_dotenv()

# JWT配置
SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(64))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# API Key配置（用于后端服务间调用）
MASTER_API_KEY = os.getenv("MASTER_API_KEY", secrets.token_urlsafe(32))

security = HTTPBearer()

# ============================================================================
# Pydantic模型
# ============================================================================

class Token(BaseModel):
    """Token响应"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = ACCESS_TOKEN_EXPIRE_MINUTES * 60
    username: str = ""
    is_admin: bool = False
    scopes: list = []

class TokenData(BaseModel):
    """Token数据"""
    username: Optional[str] = None
    scopes: list = []

class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str

class User(BaseModel):
    """用户模型（包含数据库ID）"""
    id: Optional[int] = None  # 数据库用户ID
    username: str
    is_admin: bool = False
    scopes: list = ["read", "write"]
    
    class Config:
        from_attributes = True

# ============================================================================
# 用户验证（使用真实数据库）
# ============================================================================

# 保留临时用户数据库作为后备（仅用于初始化）
USERS_DB_FALLBACK = {
    "admin": {
        "username": "admin",
        "password_hash": hashlib.sha256("admin123".encode()).hexdigest(),  # 默认密码
        "is_admin": True,
        "scopes": ["read", "write", "admin"]
    }
}

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return hashlib.sha256(plain_password.encode()).hexdigest() == hashed_password

def authenticate_user(username: str, password: str, db: Session) -> Optional[User]:
    """认证用户（从数据库）"""
    # 从数据库查找用户
    db_user = db.query(DBUser).filter(DBUser.username == username).first()
    
    if not db_user:
        # 如果数据库中没有，检查后备字典（用于初始化）
        user_data = USERS_DB_FALLBACK.get(username)
        if not user_data:
            return None
        if not verify_password(password, user_data["password_hash"]):
            return None
        
        # 如果验证成功且是后备用户，创建数据库用户
        if username == "admin":
            # 创建admin用户到数据库
            db_user = DBUser(
                username=user_data["username"],
                hashed_password=user_data["password_hash"],
                is_admin=True,
                is_active=True
            )
            db.add(db_user)
            db.commit()
            db.refresh(db_user)
            
            return User(
                id=db_user.id,
                username=db_user.username,
                is_admin=db_user.is_admin,
                scopes=user_data["scopes"]
            )
        else:
            # 非admin后备用户，返回None（不允许自动创建）
            return None
    
    # 验证密码
    if not verify_password(password, db_user.hashed_password):
        return None
    
    # 检查用户是否激活
    if not db_user.is_active:
        return None
    
    # 确定权限范围
    if db_user.is_admin:
        scopes = ["read", "write", "admin"]
    else:
        scopes = ["read", "write"]
    
    return User(
        id=db_user.id,
        username=db_user.username,
        is_admin=db_user.is_admin,
        scopes=scopes
    )

# ============================================================================
# JWT Token操作
# ============================================================================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建JWT访问令牌
    
    Args:
        data: 要编码的数据
        expires_delta: 过期时间增量
    
    Returns:
        JWT token字符串
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> TokenData:
    """
    验证JWT token
    
    Args:
        token: JWT token字符串
    
    Returns:
        TokenData对象
    
    Raises:
        HTTPException: token无效或过期
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        scopes: list = payload.get("scopes", [])
        
        if username is None:
            raise credentials_exception
        
        return TokenData(username=username, scopes=scopes)
        
    except JWTError as e:
        # 检查是否是过期错误
        if "expired" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token已过期",
                headers={"WWW-Authenticate": "Bearer"},
            )
        else:
            raise credentials_exception

# ============================================================================
# 依赖函数（用于FastAPI路由）
# ============================================================================

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    获取当前用户（需要有效token，从数据库获取）
    
    用法：
        @router.get("/protected")
        async def protected_route(user: User = Depends(get_current_user)):
            return {"message": f"Hello {user.username}"}
    """
    token = credentials.credentials
    token_data = verify_token(token)
    
    # 从数据库查找用户
    db_user = db.query(DBUser).filter(DBUser.username == token_data.username).first()
    
    if db_user is None:
        # 如果数据库中没有，检查后备字典
        user_data = USERS_DB_FALLBACK.get(token_data.username)
        if user_data is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户不存在"
            )
        
        # 返回后备用户（没有id，这是临时情况）
        return User(
            id=None,  # 后备用户没有数据库ID
            username=user_data["username"],
            is_admin=user_data["is_admin"],
            scopes=user_data["scopes"]
        )
    
    # 检查用户是否激活
    if not db_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户账户已被禁用"
        )
    
    # 确定权限范围
    if db_user.is_admin:
        scopes = ["read", "write", "admin"]
    else:
        scopes = ["read", "write"]
    
    return User(
        id=db_user.id,
        username=db_user.username,
        is_admin=db_user.is_admin,
        scopes=scopes
    )

async def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    获取当前管理员用户
    
    用法：
        @router.delete("/admin/delete")
        async def admin_only_route(admin: User = Depends(get_current_admin_user)):
            return {"message": "Admin access granted"}
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    return current_user

# ============================================================================
# API Key认证（可选，用于服务间调用）
# ============================================================================

def verify_api_key(api_key: str) -> bool:
    """验证API密钥"""
    return api_key == MASTER_API_KEY

async def verify_api_key_header(request: Request) -> bool:
    """
    从请求头验证API密钥
    
    用法：
        @router.get("/api/internal")
        async def internal_api(verified: bool = Depends(verify_api_key_header)):
            return {"message": "Internal API"}
    """
    api_key = request.headers.get("X-API-Key")
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少API密钥"
        )
    
    if not verify_api_key(api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的API密钥"
        )
    
    return True

# ============================================================================
# 可选认证（用于部分公开的端点）
# ============================================================================

async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    获取当前用户（可选）
    如果提供token则验证，否则返回None
    
    用法：
        @router.get("/public")
        async def public_route(user: Optional[User] = Depends(get_current_user_optional)):
            if user:
                return {"message": f"Hello {user.username}"}
            return {"message": "Hello guest"}
    """
    if credentials is None:
        return None
    
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None

# ============================================================================
# 登录端点（示例）
# ============================================================================

from fastapi import APIRouter

router = APIRouter(prefix="/api/auth", tags=["认证"])

@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    用户登录（OAuth2 兼容，使用数据库验证）
    
    支持 application/x-www-form-urlencoded 格式：
    - username: 用户名
    - password: 密码
    
    响应示例：
    ```json
    {
        "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
        "token_type": "bearer",
        "expires_in": 1800
    }
    ```
    """
    user = authenticate_user(form_data.username, form_data.password, db)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 创建访问令牌
    access_token = create_access_token(
        data={
            "sub": user.username,
            "scopes": user.scopes,
            "is_admin": user.is_admin
        }
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        username=user.username,
        is_admin=user.is_admin,
        scopes=user.scopes
    )

@router.get("/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    获取当前用户信息
    
    需要在请求头中包含：
    ```
    Authorization: Bearer <token>
    ```
    """
    return current_user

@router.post("/refresh")
async def refresh_token(current_user: User = Depends(get_current_user)):
    """
    刷新token
    
    返回新的访问令牌
    """
    new_token = create_access_token(
        data={
            "sub": current_user.username,
            "scopes": current_user.scopes,
            "is_admin": current_user.is_admin
        }
    )
    
    return Token(
        access_token=new_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

# ============================================================================
# 用户管理（管理员功能）
# ============================================================================

class UserCreateRequest(BaseModel):
    """创建用户请求"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, description="密码")
    is_admin: bool = Field(default=False, description="是否为管理员")
    scopes: list = Field(default=["read", "write"], description="权限列表")

class UserResponse(BaseModel):
    """用户响应"""
    username: str
    is_admin: bool
    scopes: list
    created_at: str

class PasswordChangeRequest(BaseModel):
    """修改密码请求"""
    old_password: str
    new_password: str = Field(..., min_length=6)

class PasswordResetRequest(BaseModel):
    """重置密码请求（管理员）"""
    new_password: str = Field(..., min_length=6)

@router.post("/register", response_model=UserResponse)
async def register_user(
    user_request: UserCreateRequest,
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    注册新用户（仅管理员可用，保存到数据库）
    
    管理员可以创建新用户并设置权限
    
    请求示例：
    ```json
    {
        "username": "trader1",
        "password": "secure_password_123",
        "is_admin": false,
        "scopes": ["read", "write"]
    }
    ```
    """
    # 检查用户是否已存在（数据库）
    existing_user = db.query(DBUser).filter(DBUser.username == user_request.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"用户 '{user_request.username}' 已存在"
        )
    
    # 创建用户到数据库
    password_hash = hashlib.sha256(user_request.password.encode()).hexdigest()
    
    db_user = DBUser(
        username=user_request.username,
        hashed_password=password_hash,
        is_admin=user_request.is_admin,
        is_active=True
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return UserResponse(
        username=db_user.username,
        is_admin=db_user.is_admin,
        scopes=user_request.scopes,
        created_at=db_user.created_at.isoformat() if db_user.created_at else datetime.utcnow().isoformat()
    )

@router.get("/users", response_model=list)
async def list_users(
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    获取所有用户列表（仅管理员可用，从数据库读取）
    
    返回所有用户的基本信息（不包含密码）
    """
    db_users = db.query(DBUser).all()
    
    users = []
    for db_user in db_users:
        scopes = ["read", "write", "admin"] if db_user.is_admin else ["read", "write"]
        users.append({
            "id": db_user.id,
            "username": db_user.username,
            "is_admin": db_user.is_admin,
            "is_active": db_user.is_active,
            "scopes": scopes,
            "created_at": db_user.created_at.isoformat() if db_user.created_at else "unknown"
        })
    
    return users

@router.delete("/users/{username}")
async def delete_user(
    username: str,
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    删除用户（仅管理员可用，从数据库删除）
    
    注意：不能删除自己的账号
    """
    if username == admin.username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能删除自己的账号"
        )
    
    db_user = db.query(DBUser).filter(DBUser.username == username).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"用户 '{username}' 不存在"
        )
    
    # 删除用户及其配置（从数据库）
    # TODO: 同时删除该用户的所有配置数据（如果需要级联删除）
    
    db.delete(db_user)
    db.commit()
    
    return {
        "success": True,
        "message": f"用户 '{username}' 已删除"
    }

@router.put("/change-password")
async def change_password(
    request: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    修改密码（更新到数据库）
    
    用户可以修改自己的密码
    """
    db_user = db.query(DBUser).filter(DBUser.username == current_user.username).first()
    
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 验证旧密码
    if not verify_password(request.old_password, db_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="旧密码错误"
        )
    
    # 更新密码
    new_password_hash = hashlib.sha256(request.new_password.encode()).hexdigest()
    db_user.hashed_password = new_password_hash
    db.commit()
    
    return {
        "success": True,
        "message": "密码已更新"
    }

@router.put("/users/{username}/reset-password")
async def reset_user_password(
    username: str,
    request: PasswordResetRequest,
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    重置用户密码（仅管理员可用，更新到数据库）
    
    管理员可以重置任何用户的密码
    """
    db_user = db.query(DBUser).filter(DBUser.username == username).first()
    
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"用户 '{username}' 不存在"
        )
    
    # 更新密码
    new_password_hash = hashlib.sha256(request.new_password.encode()).hexdigest()
    db_user.hashed_password = new_password_hash
    db.commit()
    
    return {
        "success": True,
        "message": f"用户 '{username}' 的密码已重置"
    }

# ============================================================================
# 使用示例
# ============================================================================

"""
在其他API模块中使用认证：

from api_auth import get_current_user, get_current_admin_user, User

# 需要登录
@router.get("/protected")
async def protected_route(user: User = Depends(get_current_user)):
    return {"message": f"Hello {user.username}"}

# 需要管理员权限
@router.delete("/admin/delete")
async def admin_route(admin: User = Depends(get_current_admin_user)):
    return {"message": "Admin only"}

# 可选登录（公开但可识别用户）
@router.get("/public")
async def public_route(user: Optional[User] = Depends(get_current_user_optional)):
    if user:
        return {"message": f"Hello {user.username}"}
    return {"message": "Hello guest"}
"""

# ============================================================================
# 前端使用示例
# ============================================================================

"""
前端JavaScript/TypeScript示例：

// 1. 登录
const login = async (username: string, password: string) => {
    const res = await fetch('http://localhost:8000/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
    });
    
    const data = await res.json();
    
    if (res.ok) {
        // 保存token
        localStorage.setItem('access_token', data.access_token);
        return data;
    } else {
        throw new Error(data.detail);
    }
};

// 2. 调用受保护的API
const callProtectedAPI = async () => {
    const token = localStorage.getItem('access_token');
    
    const res = await fetch('http://localhost:8000/api/config/update', {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`  // 添加token
        },
        body: JSON.stringify({
            category: 'deepseek',
            config: { api_key: 'sk-xxx' }
        })
    });
    
    if (res.status === 401) {
        // Token过期，重新登录
        window.location.href = '/login';
    }
    
    return res.json();
};

// 3. 自动刷新token
const refreshToken = async () => {
    const token = localStorage.getItem('access_token');
    
    const res = await fetch('http://localhost:8000/api/auth/refresh', {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${token}`
        }
    });
    
    const data = await res.json();
    localStorage.setItem('access_token', data.access_token);
};

// 4. 拦截器（自动添加token）
axios.interceptors.request.use(config => {
    const token = localStorage.getItem('access_token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// 5. 响应拦截器（处理401）
axios.interceptors.response.use(
    response => response,
    error => {
        if (error.response.status === 401) {
            localStorage.removeItem('access_token');
            window.location.href = '/login';
        }
        return Promise.reject(error);
    }
);
"""

if __name__ == "__main__":
    print("=" * 80)
    print("🔐 API认证模块")
    print("=" * 80)
    print("\n功能：")
    print("  • JWT Token认证")
    print("  • 用户权限管理")
    print("  • Token自动过期")
    print("  • API Key认证（服务间）")
    print("  • 可选认证支持")
    print("\n默认管理员账号：")
    print("  用户名: admin")
    print("  密码: admin123")
    print("\n⚠️ 生产环境请务必修改默认密码！")
    print("=" * 80)
    
    # 测试token创建
    print("\n测试JWT Token创建：")
    token = create_access_token(data={"sub": "admin", "scopes": ["read", "write", "admin"]})
    print(f"Token: {token[:50]}...")
    print(f"长度: {len(token)} 字符")
    
    # 测试token验证
    print("\n测试Token验证：")
    token_data = verify_token(token)
    print(f"✅ Token有效")
    print(f"用户: {token_data.username}")
    print(f"权限: {token_data.scopes}")


# ============================================================================
# WebSocket Token 验证
# ============================================================================

def verify_token_ws(token: str, db: Session = None) -> dict:
    """
    WebSocket Token 验证（从数据库获取用户信息）
    
    用于WebSocket连接的token验证，返回用户数据字典
    
    Args:
        token: JWT token字符串
        db: 数据库会话（可选）
    
    Returns:
        dict: 用户数据字典，包含 user_id, username, is_admin, scopes
        None: token无效
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        
        if username is None:
            return None
        
        # 如果提供了数据库会话，从数据库查找
        if db:
            db_user = db.query(DBUser).filter(DBUser.username == username).first()
            if db_user:
                scopes = ["read", "write", "admin"] if db_user.is_admin else ["read", "write"]
                return {
                    "user_id": db_user.id,
                    "username": db_user.username,
                    "is_admin": db_user.is_admin,
                    "scopes": scopes
                }
        
        # 后备：从内存字典查找（向后兼容）
        user_data = USERS_DB_FALLBACK.get(username)
        if not user_data:
            return None
        
        # 返回用户信息
        return {
            "user_id": None,  # 后备用户没有数据库ID
            "username": username,
            "is_admin": user_data.get("is_admin", False),
            "scopes": user_data.get("scopes", [])
        }
        
    except JWTError:
        return None
