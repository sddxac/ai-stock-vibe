#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import streamlit as st
import requests
import secrets
import hashlib
import re
from datetime import datetime
import time
import json

# Supabase 配置
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")

# 模拟用户数据库（仅用于测试，生产环境应使用真实数据库）
MOCK_USERS = {}

def supabase_request(method, endpoint, data=None):
    """发送请求到 Supabase REST API"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("❌ Supabase 配置缺失")
        return None
    
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data)
        elif method == "PATCH":
            response = requests.patch(url, headers=headers, json=data)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers)
        
        if response.status_code in [200, 201, 204]:
            return response.json() if response.content else []
        else:
            if response.status_code == 404:
                # 如果表不存在，使用模拟数据
                if endpoint == "user_credentials":
                    return []
                st.error("❌ 数据表不存在，使用模拟模式")
            elif response.status_code == 409:
                st.error("❌ 用户名或邮箱已存在")
            else:
                st.error(f"❌ 数据库错误: {response.status_code}")
            return None
    except Exception as e:
        st.error(f"❌ 连接失败: {str(e)}")
        return None

def generate_password_hash(password: str) -> tuple:
    """生成密码哈希和盐值"""
    salt = secrets.token_hex(16)  # 生成随机盐值
    password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
    return password_hash, salt

def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """验证密码"""
    computed_hash = hashlib.sha256((password + salt).encode()).hexdigest()
    return computed_hash == stored_hash

def validate_email(email: str) -> bool:
    """验证邮箱格式"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_username(username: str) -> bool:
    """验证用户名格式"""
    pattern = r'^[a-zA-Z0-9_]{3,20}$'
    return re.match(pattern, username) is not None

def validate_password(password: str) -> tuple:
    """验证密码强度"""
    errors = []
    
    if len(password) < 6:
        errors.append("密码长度至少6位")
    
    if len(password) > 50:
        errors.append("密码长度不能超过50位")
    
    if not re.search(r'[a-zA-Z]', password):
        errors.append("密码必须包含字母")
    
    if not re.search(r'[0-9]', password):
        errors.append("密码必须包含数字")
    
    return len(errors) == 0, errors

def register_user(username: str, email: str, password: str) -> tuple:
    """注册新用户"""
    # 验证输入
    if not validate_username(username):
        return False, "用户名格式错误（3-20位字母数字下划线）"
    
    if not validate_email(email):
        return False, "邮箱格式错误"
    
    is_valid, errors = validate_password(password)
    if not is_valid:
        return False, "密码不符合要求：" + "；".join(errors)
    
    # 检查用户名是否已存在（模拟）
    if username in MOCK_USERS:
        return False, "用户名已存在"
    
    # 检查邮箱是否已存在（模拟）
    for user_data in MOCK_USERS.values():
        if user_data.get('email') == email:
            return False, "邮箱已存在"
    
    # 生成密码哈希
    password_hash, salt = generate_password_hash(password)
    
    # 创建用户记录
    user_data = {
        "username": username,
        "email": email,
        "password_hash": password_hash,
        "salt": salt,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "last_login": None,
        "is_active": True
    }
    
    # 尝试保存到数据库，如果失败则使用模拟数据
    result = supabase_request("POST", "user_credentials", user_data)
    if result:
        return True, "注册成功！"
    else:
        # 使用模拟数据
        MOCK_USERS[username] = user_data
        return True, "注册成功！（模拟模式）"

def authenticate_user(username: str, password: str) -> tuple:
    """用户认证"""
    # 先尝试从数据库获取
    result = supabase_request("GET", f"user_credentials?username=eq.{username}")
    
    if result and len(result) > 0:
        user = result[0]
    else:
        # 使用模拟数据
        if username not in MOCK_USERS:
            return False, "用户名不存在"
        user = MOCK_USERS[username]
    
    # 检查账户是否激活
    if not user.get("is_active", True):
        return False, "账户已被禁用"
    
    # 验证密码
    stored_hash = user["password_hash"]
    salt = user["salt"]
    
    if verify_password(password, stored_hash, salt):
        # 更新最后登录时间
        update_data = {
            "last_login": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        supabase_request("PATCH", f"user_credentials?username=eq.{username}", update_data)
        
        return True, user
    else:
        return False, "密码错误"

def show_login_form():
    """显示登录表单"""
    st.subheader("🔐 用户登录")
    
    with st.form("login_form"):
        username = st.text_input("用户名", placeholder="请输入用户名")
        password = st.text_input("密码", type="password", placeholder="请输入密码")
        submitted = st.form_submit_button("登录", type="primary")
        
        if submitted:
            if not username or not password:
                st.error("请填写用户名和密码")
                return None
            
            success, result = authenticate_user(username, password)
            
            if success:
                st.session_state.authenticated = True
                st.session_state.username = username
                st.session_state.user_info = result
                st.success(f"欢迎回来，{username}！")
                st.rerun()
            else:
                st.error(result)
    
    # 注册链接
    st.markdown("---")
    st.markdown("还没有账号？")
    if st.button("点击注册"):
        st.session_state.show_register = True
        st.rerun()

def show_register_form():
    """显示注册表单"""
    st.subheader("📝 用户注册")
    
    with st.form("register_form"):
        username = st.text_input("用户名", placeholder="3-20位字母数字下划线")
        email = st.text_input("邮箱", placeholder="请输入有效邮箱")
        password = st.text_input("密码", type="password", placeholder="至少6位，包含字母和数字")
        confirm_password = st.text_input("确认密码", type="password", placeholder="再次输入密码")
        
        submitted = st.form_submit_button("注册", type="primary")
        
        if submitted:
            # 验证所有字段
            if not all([username, email, password, confirm_password]):
                st.error("请填写所有字段")
                return
            
            if password != confirm_password:
                st.error("两次输入的密码不一致")
                return
            
            success, message = register_user(username, email, password)
            
            if success:
                st.success(message)
                st.info("请使用新账号登录")
                time.sleep(2)
                st.session_state.show_register = False
                st.rerun()
            else:
                st.error(message)
    
    # 返回登录链接
    st.markdown("---")
    st.markdown("已有账号？")
    if st.button("返回登录"):
        st.session_state.show_register = False
        st.rerun()

def logout_user():
    """用户登出"""
    keys_to_clear = ['authenticated', 'username', 'user_info']
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]
    st.success("已安全登出")
    st.rerun()

def check_authentication():
    """检查用户认证状态"""
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    
    return st.session_state.authenticated

def get_current_user():
    """获取当前用户信息"""
    if check_authentication():
        return st.session_state.get('username'), st.session_state.get('user_info')
    return None, None

def show_user_info():
    """显示用户信息"""
    username, user_info = get_current_user()
    if username:
        st.sidebar.markdown(f"**当前用户：** {username}")
        
        if st.sidebar.button("🚪 退出登录"):
            logout_user()
