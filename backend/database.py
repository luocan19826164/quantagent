"""
数据库管理模块
处理用户认证和规则存储 (SQLite)
"""

import sqlite3
import hashlib
import json
import os
from datetime import datetime

DB_PATH = 'quant.db'

def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """初始化数据库表"""
    conn = get_db_connection()
    c = conn.cursor()
    
    # 用户表
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 规则表
    c.execute('''
        CREATE TABLE IF NOT EXISTS saved_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            rule_content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def hash_password(password):
    """简单的密码哈希 (SHA256)"""
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(username, password):
    """创建新用户"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        pwd_hash = hash_password(password)
        c.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', 
                  (username, pwd_hash))
        conn.commit()
        user_id = c.lastrowid
        conn.close()
        return user_id
    except sqlite3.IntegrityError:
        return None  # 用户名已存在
    except Exception as e:
        print(f"Database error: {e}")
        return None

def verify_user(username, password):
    """验证用户登录"""
    conn = get_db_connection()
    c = conn.cursor()
    pwd_hash = hash_password(password)
    c.execute('SELECT * FROM users WHERE username = ? AND password_hash = ?', 
              (username, pwd_hash))
    user = c.fetchone()
    conn.close()
    return user

def get_user_by_id(user_id):
    """根据ID获取用户"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT id, username FROM users WHERE id = ?', (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def save_rule(user_id, rule_content):
    """保存规则"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # 确保存储的是JSON字符串
        if isinstance(rule_content, dict):
            content_str = json.dumps(rule_content, ensure_ascii=False)
        else:
            content_str = rule_content
            
        c.execute('INSERT INTO saved_rules (user_id, rule_content) VALUES (?, ?)', 
                  (user_id, content_str))
        conn.commit()
        rule_id = c.lastrowid
        conn.close()
        return rule_id
    except Exception as e:
        print(f"Save rule error: {e}")
        return None

def get_user_rules(user_id):
    """获取用户的所有规则"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM saved_rules WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
    rules = c.fetchall()
    conn.close()
    
    # 转换回字典列表
    result = []
    for r in rules:
        try:
            content = json.loads(r['rule_content'])
        except:
            content = r['rule_content']
            
        result.append({
            "id": r['id'],
            "created_at": r['created_at'],
            "content": content
        })
    return result
