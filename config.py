# -*- coding: utf-8 -*-
"""
PDF元数据提取系统配置文件
"""

import os
from pathlib import Path

class Config:
    """基础配置"""
    # 应用配置
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'pdf-metadata-extractor-secret-key'
    
    # 文件上传配置
    UPLOAD_FOLDER = 'uploads'
    RESULTS_FOLDER = 'results'
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB
    ALLOWED_EXTENSIONS = {'pdf'}
    
    # API配置
    API_RATE_LIMIT = "100 per minute"
    
    # LLM配置
    LLM_API_KEY = os.environ.get('LLM_API_KEY') or 'sk-bd884acabfc8420fb852bbdd86fa276a'
    LLM_API_ENDPOINT = os.environ.get('LLM_API_ENDPOINT') or "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    LLM_MODEL = os.environ.get('LLM_MODEL') or "qwen-flash"
    LLM_MAX_TOKENS = int(os.environ.get('LLM_MAX_TOKENS', '4000'))
    LLM_TEMPERATURE = float(os.environ.get('LLM_TEMPERATURE', '0.1'))
    
    # 日志配置
    LOG_LEVEL = os.environ.get('LOG_LEVEL') or 'INFO'
    LOG_FILE = 'pdf_extraction.log'
    
    @classmethod
    def init_app(cls, app):
        """初始化应用配置"""
        # 创建必要的目录
        for folder in [cls.UPLOAD_FOLDER, cls.RESULTS_FOLDER]:
            Path(folder).mkdir(exist_ok=True)
        
        # 设置Flask配置
        app.config['UPLOAD_FOLDER'] = cls.UPLOAD_FOLDER
        app.config['MAX_CONTENT_LENGTH'] = cls.MAX_CONTENT_LENGTH
        app.config['SECRET_KEY'] = cls.SECRET_KEY

class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG = True
    
class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG = False
    
    # 生产环境安全配置
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

class TestingConfig(Config):
    """测试环境配置"""
    TESTING = True
    UPLOAD_FOLDER = 'test_uploads'
    RESULTS_FOLDER = 'test_results'

# 配置映射
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
