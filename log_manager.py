# -*- coding: utf-8 -*-
"""
日志管理模块
支持按IP地址+时间命名的日志文件，记录访问者操作信息
"""

import os
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from flask import request, g
import json

class LogManager:
    """日志管理器"""
    
    def __init__(self, log_dir: str = "log"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.loggers = {}  # 缓存logger实例
        
    def _get_client_ip(self) -> str:
        """获取客户端IP地址"""
        # 获取真实IP地址，考虑代理情况
        if request.headers.get('X-Forwarded-For'):
            return request.headers.get('X-Forwarded-For').split(',')[0].strip()
        elif request.headers.get('X-Real-IP'):
            return request.headers.get('X-Real-IP')
        elif request.headers.get('X-Client-IP'):
            return request.headers.get('X-Client-IP')
        else:
            return request.remote_addr or 'unknown'
    
    def _generate_log_filename(self, ip: str) -> str:
        """生成日志文件名：IP_YYYYMMDD_HHMMSS.log"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 清理IP地址中的特殊字符
        clean_ip = ip.replace('.', '_').replace(':', '_')
        return f"{clean_ip}_{timestamp}.log"
    
    def _get_logger(self, ip: str) -> logging.Logger:
        """获取指定IP的logger实例"""
        if ip in self.loggers:
            return self.loggers[ip]
        
        # 创建新的logger
        filename = self._generate_log_filename(ip)
        log_file = self.log_dir / filename
        
        # 创建logger
        logger = logging.getLogger(f"user_{ip}")
        logger.setLevel(logging.INFO)
        
        # 避免重复添加handler
        if not logger.handlers:
            # 文件handler
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.INFO)
            
            # 控制台handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            
            # 格式化器
            formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            
            file_handler.setFormatter(formatter)
            console_handler.setFormatter(formatter)
            
            logger.addHandler(file_handler)
            logger.addHandler(console_handler)
        
        self.loggers[ip] = logger
        return logger
    
    def log_operation(self, operation: str, details: Dict[str, Any] = None, 
                     processing_time: float = None, status: str = "success"):
        """记录操作日志"""
        try:
            ip = self._get_client_ip()
            logger = self._get_logger(ip)
            
            # 构建日志消息
            log_data = {
                "timestamp": datetime.now().isoformat(),
                "ip": ip,
                "operation": operation,
                "status": status,
                "processing_time": processing_time,
                "details": details or {}
            }
            
            # 记录到日志文件
            if status == "success":
                logger.info(f"[{ip}] {operation} - 成功")
                if processing_time:
                    logger.info(f"[{ip}] 处理耗时: {processing_time:.2f}秒")
                if details:
                    logger.info(f"[{ip}] 详细信息: {json.dumps(details, ensure_ascii=False)}")
            else:
                logger.error(f"[{ip}] {operation} - 失败")
                if details and 'error' in details:
                    logger.error(f"[{ip}] 错误信息: {details['error']}")
                if processing_time:
                    logger.error(f"[{ip}] 处理耗时: {processing_time:.2f}秒")
            
            # 记录到Flask的g对象中，方便其他地方使用
            if not hasattr(g, 'operation_logs'):
                g.operation_logs = []
            g.operation_logs.append(log_data)
            
        except Exception as e:
            # 如果日志记录失败，至少打印到控制台
            print(f"日志记录失败: {e}")
    
    def log_file_upload(self, filename: str, file_size: int, processing_time: float = None):
        """记录文件上传日志"""
        details = {
            "filename": filename,
            "file_size": file_size,
            "file_size_mb": round(file_size / (1024 * 1024), 2)
        }
        self.log_operation("文件上传", details, processing_time)
    
    def log_file_processing(self, filename: str, mode: str, processing_time: float = None, 
                          status: str = "success", error: str = None):
        """记录文件处理日志"""
        details = {
            "filename": filename,
            "mode": mode,
            "error": error
        }
        self.log_operation("文件处理", details, processing_time, status)
    
    def log_batch_processing(self, file_count: int, mode: str, processing_time: float = None,
                           success_count: int = 0, failed_count: int = 0):
        """记录批量处理日志"""
        details = {
            "file_count": file_count,
            "mode": mode,
            "success_count": success_count,
            "failed_count": failed_count,
            "success_rate": round(success_count / file_count * 100, 2) if file_count > 0 else 0
        }
        self.log_operation("批量处理", details, processing_time)
    
    def log_api_call(self, endpoint: str, method: str, processing_time: float = None,
                    status_code: int = 200, error: str = None):
        """记录API调用日志"""
        details = {
            "endpoint": endpoint,
            "method": method,
            "status_code": status_code,
            "error": error
        }
        status = "success" if status_code < 400 else "error"
        self.log_operation("API调用", details, processing_time, status)
    
    def log_system_info(self, info_type: str, details: Dict[str, Any] = None):
        """记录系统信息日志"""
        self.log_operation(f"系统信息-{info_type}", details)
    
    def get_user_logs(self, ip: str, limit: int = 100) -> list:
        """获取指定IP用户的日志记录"""
        try:
            if not hasattr(g, 'operation_logs'):
                return []
            
            user_logs = [log for log in g.operation_logs if log.get('ip') == ip]
            return user_logs[-limit:]  # 返回最新的记录
        except Exception:
            return []
    
    def cleanup_old_logs(self, days: int = 30):
        """清理指定天数之前的旧日志文件"""
        try:
            current_time = time.time()
            cutoff_time = current_time - (days * 24 * 60 * 60)
            
            deleted_count = 0
            for log_file in self.log_dir.glob("*.log"):
                if log_file.stat().st_mtime < cutoff_time:
                    log_file.unlink()
                    deleted_count += 1
            
            if deleted_count > 0:
                print(f"清理了 {deleted_count} 个旧日志文件")
                
        except Exception as e:
            print(f"清理旧日志失败: {e}")

# 全局日志管理器实例
log_manager = LogManager()

# 便捷函数
def log_operation(operation: str, details: Dict[str, Any] = None, 
                 processing_time: float = None, status: str = "success"):
    """记录操作日志的便捷函数"""
    log_manager.log_operation(operation, details, processing_time, status)

def log_file_upload(filename: str, file_size: int, processing_time: float = None):
    """记录文件上传日志的便捷函数"""
    log_manager.log_file_upload(filename, file_size, processing_time)

def log_file_processing(filename: str, mode: str, processing_time: float = None, 
                       status: str = "success", error: str = None):
    """记录文件处理日志的便捷函数"""
    log_manager.log_file_processing(filename, mode, processing_time, status, error)

def log_batch_processing(file_count: int, mode: str, processing_time: float = None,
                        success_count: int = 0, failed_count: int = 0):
    """记录批量处理日志的便捷函数"""
    log_manager.log_batch_processing(file_count, mode, processing_time, success_count, failed_count)

def log_api_call(endpoint: str, method: str, processing_time: float = None,
                status_code: int = 200, error: str = None):
    """记录API调用日志的便捷函数"""
    log_manager.log_api_call(endpoint, method, processing_time, status_code, error)
