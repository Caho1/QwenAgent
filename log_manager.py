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
        self.session_logs = {}  # 会话级别的日志缓存
        
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
    
    def _generate_log_filename(self, ip: str, session_id: str = None) -> str:
        """生成日志文件名：IP_YYYYMMDD_HHMMSS.log 或 IP_YYYYMMDD_HHMMSS_SESSION.log"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 清理IP地址中的特殊字符
        clean_ip = ip.replace('.', '_').replace(':', '_')
        if session_id:
            return f"{clean_ip}_{timestamp}_{session_id}.log"
        return f"{clean_ip}_{timestamp}.log"

    def _get_session_id(self) -> str:
        """获取或生成会话ID"""
        if not hasattr(g, 'session_id'):
            import uuid
            g.session_id = str(uuid.uuid4())[:8]  # 使用短UUID作为会话ID
        return g.session_id
    
    def _get_logger(self, ip: str, session_id: str = None) -> logging.Logger:
        """获取指定IP的logger实例（合并日志文件）"""
        # 使用会话ID作为logger的key
        logger_key = f"{ip}_{session_id}" if session_id else ip

        if logger_key in self.loggers:
            return self.loggers[logger_key]

        # 创建新的logger
        logger = logging.getLogger(f"user_{logger_key}")
        logger.setLevel(logging.INFO)

        # 清除现有的handlers
        logger.handlers.clear()

        # 创建文件handler，写入到指定的日志文件
        log_filename = self._generate_log_filename(ip, session_id)
        log_filepath = self.log_dir / log_filename

        file_handler = logging.FileHandler(log_filepath, mode='w', encoding='utf-8')
        file_handler.setLevel(logging.INFO)

        # 设置简单的格式，不包含时间戳等前缀
        formatter = logging.Formatter('%(message)s')
        file_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.propagate = False

        self.loggers[logger_key] = logger
        return logger
    
    def log_operation(self, operation: str, details: Dict[str, Any] = None,
                     processing_time: float = None, status: str = "success", tokens_used: int = None):
        """记录操作日志（精简版）- 仅用于调试，不写入最终日志文件"""
        try:
            # 只在控制台输出调试信息，不写入日志文件
            if status == "success":
                log_msg = f"[{operation}] 成功"
                if processing_time:
                    log_msg += f" | 耗时: {processing_time:.2f}秒"
                if tokens_used:
                    log_msg += f" | Tokens: {tokens_used:,}"
                print(log_msg)  # 只输出到控制台
            else:
                log_msg = f"[{operation}] 失败"
                if details and 'error' in details:
                    log_msg += f" | 错误: {details['error']}"
                if processing_time:
                    log_msg += f" | 耗时: {processing_time:.2f}秒"
                print(log_msg)  # 只输出到控制台

        except Exception as e:
            # 如果日志记录失败，至少打印到控制台
            print(f"日志记录失败: {e}")
    
    def start_upload_session(self, total_files: int, mode: str = None):
        """开始上传会话"""
        ip = self._get_client_ip()
        session_id = self._get_session_id()
        session_key = f"{ip}_{session_id}"

        self.session_logs[session_key] = {
            "session_id": session_id,
            "ip": ip,
            "start_time": time.time(),
            "total_files": total_files,
            "mode": mode,
            "uploaded_files": [],
            "processed_files": [],
            "errors": [],
            "upload_tokens": 0, # 新增：记录上传tokens
            "processing_tokens": 0 # 新增：记录处理tokens
        }

        # 记录会话开始（仅控制台输出）
        details = {
            "session_id": session_id,
            "total_files": total_files,
            "mode": mode or "未指定"
        }
        self.log_operation("上传会话开始", details)
        return session_key

    def log_file_upload(self, filename: str, file_size: int, processing_time: float = None):
        """记录单个文件上传"""
        ip = self._get_client_ip()
        session_id = self._get_session_id()
        session_key = f"{ip}_{session_id}"

        # 添加到会话记录
        if session_key in self.session_logs:
            self.session_logs[session_key]["uploaded_files"].append({
                "filename": filename,
                "file_size": file_size,
                "upload_time": time.time()
            })

        # 记录详细的单个文件上传信息（仅控制台调试用）
        details = {
            "filename": filename,
            "file_size": file_size,
            "file_size_mb": round(file_size / (1024 * 1024), 2),
            "session_id": session_id
        }
        # 注释掉，避免在日志文件中记录中间过程
        # self.log_operation("单个文件上传", details, processing_time)

    def add_tokens_to_session(self, upload_tokens: int = 0, processing_tokens: int = 0):
        """向当前会话添加tokens统计"""
        ip = self._get_client_ip()
        session_id = self._get_session_id()
        session_key = f"{ip}_{session_id}"

        if session_key in self.session_logs:
            self.session_logs[session_key]["upload_tokens"] += upload_tokens
            self.session_logs[session_key]["processing_tokens"] += processing_tokens

    def update_session_mode(self, new_mode: str):
        """更新当前会话的处理模式，而不创建新会话"""
        ip = self._get_client_ip()
        session_id = self._get_session_id()
        session_key = f"{ip}_{session_id}"

        if session_key in self.session_logs:
            self.session_logs[session_key]["mode"] = new_mode
            return session_key
        else:
            # 如果没有现有会话，创建一个新的
            return self.start_upload_session(0, new_mode)

    def log_file_processing(self, filename: str, mode: str, processing_time: float = None,
                          status: str = "success", error: str = None,
                          prompt_tokens: int = 0, completion_tokens: int = 0, total_tokens: int = 0):
        """记录单个文件处理（精简版）"""
        ip = self._get_client_ip()
        session_id = self._get_session_id()
        session_key = f"{ip}_{session_id}"

        # 添加到会话记录（仅保留关键信息）
        if session_key in self.session_logs:
            self.session_logs[session_key]["processed_files"].append({
                "filename": filename,
                "mode": mode,
                "status": status,
                "processing_time": processing_time,
                "tokens_used": {
                    "prompt": prompt_tokens,
                    "completion": completion_tokens,
                    "total": total_tokens
                }
            })

            if error:
                self.session_logs[session_key]["errors"].append({
                    "filename": filename,
                    "error": error
                })

        # 记录精简的处理信息
        details = {"error": error} if error else None
        self.log_operation("文件处理", details, processing_time, status, {
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total": total_tokens
        })
    
    def end_upload_session(self, success_count: int = None, failed_count: int = None):
        """结束上传会话并记录完整日志（合并版）"""
        ip = self._get_client_ip()
        session_id = self._get_session_id()
        session_key = f"{ip}_{session_id}"

        if session_key not in self.session_logs:
            return

        session_data = self.session_logs[session_key]
        end_time = time.time()
        total_time = end_time - session_data["start_time"]

        # 统计实际数据
        actual_uploaded = len(session_data["uploaded_files"])
        actual_processed = len(session_data["processed_files"])
        actual_errors = len(session_data["errors"])
        actual_success = actual_processed - actual_errors

        # 使用传入的统计数据或实际统计数据
        final_success = success_count if success_count is not None else actual_success
        final_failed = failed_count if failed_count is not None else actual_errors
        total_files = session_data["total_files"]

        # 获取logger（使用会话ID确保写入同一个文件）
        logger = self._get_logger(ip, session_id)

        # 计算tokens统计
        upload_tokens = session_data.get("upload_tokens", 0)
        processing_tokens = session_data.get("processing_tokens", 0)
        total_tokens_from_files = sum(file_info.get('tokens_used', {}).get('total', 0) for file_info in session_data["processed_files"])

        # 如果没有单独记录上传和处理tokens，使用总tokens
        if upload_tokens == 0 and processing_tokens == 0 and total_tokens_from_files > 0:
            # 假设上传和处理各占一半（可以根据实际情况调整）
            upload_tokens = total_tokens_from_files // 2
            processing_tokens = total_tokens_from_files - upload_tokens

        total_tokens = upload_tokens + processing_tokens

        # 写入完整的会话日志（按照期望格式）
        logger.info("=== 文件处理会话日志 ===")
        logger.info(f"会话ID: {session_id}")
        logger.info(f"客户端IP: {ip}")
        logger.info(f"开始时间: {datetime.fromtimestamp(session_data['start_time']).strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"结束时间: {datetime.fromtimestamp(end_time).strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"处理模式: {session_data['mode'] or '未指定'}")
        logger.info(f"总耗时: {total_time:.2f}秒")
        logger.info(f"处理模式: 文件上传")
        logger.info(f"预期文件数: {total_files}")
        logger.info(f"实际上传: {actual_uploaded}个文件")
        logger.info(f"实际处理: {actual_processed}个文件")
        logger.info(f"处理成功: {final_success}个文件")
        logger.info(f"处理失败: {final_failed}个文件")
        logger.info(f"成功率: {(final_success / total_files * 100) if total_files > 0 else 0:.2f}%")

        if total_tokens > 0:
            logger.info(f"上传tokens: {upload_tokens}")
            logger.info(f"处理tokens: {processing_tokens}")
            logger.info(f"总tokens: {total_tokens}")

        # 写入上传文件列表
        if session_data["uploaded_files"]:
            logger.info("")
            logger.info("=== 上传文件列表 ===")
            for i, file_info in enumerate(session_data["uploaded_files"], 1):
                logger.info(f"{i:3d}. {file_info['filename']} ({file_info['file_size']} bytes)")

        # 如果有失败的文件，列出失败信息
        if session_data["errors"]:
            logger.info("")
            logger.info("=== 处理失败文件 ===")
            for i, error_info in enumerate(session_data["errors"], 1):
                logger.info(f"{i:3d}. {error_info['filename']}: {error_info['error']}")

        # 清理会话数据
        del self.session_logs[session_key]

        return None  # 不再返回文件名，因为只有一个日志文件

    def log_batch_processing(self, file_count: int, mode: str, processing_time: float = None,
                           success_count: int = 0, failed_count: int = 0):
        """记录批量处理日志（保留兼容性）"""
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
                 processing_time: float = None, status: str = "success", tokens_used: int = None):
    """记录操作日志的便捷函数"""
    log_manager.log_operation(operation, details, processing_time, status, tokens_used)

def start_upload_session(total_files: int, mode: str = None):
    """开始上传会话的便捷函数"""
    return log_manager.start_upload_session(total_files, mode)

def end_upload_session(success_count: int = None, failed_count: int = None):
    """结束上传会话的便捷函数"""
    return log_manager.end_upload_session(success_count, failed_count)

def log_file_upload(filename: str, file_size: int, processing_time: float = None):
    """记录文件上传日志的便捷函数"""
    log_manager.log_file_upload(filename, file_size, processing_time)

def add_tokens_to_session(upload_tokens: int = 0, processing_tokens: int = 0):
    """向当前会话添加tokens统计的便捷函数"""
    log_manager.add_tokens_to_session(upload_tokens, processing_tokens)

def update_session_mode(new_mode: str):
    """更新当前会话的处理模式的便捷函数"""
    return log_manager.update_session_mode(new_mode)

def log_file_processing(filename: str, mode: str, processing_time: float = None,
                       status: str = "success", error: str = None,
                       prompt_tokens: int = 0, completion_tokens: int = 0, total_tokens: int = 0):
    """记录文件处理日志的便捷函数"""
    log_manager.log_file_processing(filename, mode, processing_time, status, error, prompt_tokens, completion_tokens, total_tokens)

def log_batch_processing(file_count: int, mode: str, processing_time: float = None,
                        success_count: int = 0, failed_count: int = 0):
    """记录批量处理日志的便捷函数"""
    log_manager.log_batch_processing(file_count, mode, processing_time, success_count, failed_count)

def log_api_call(endpoint: str, method: str, processing_time: float = None,
                status_code: int = 200, error: str = None):
    """记录API调用日志的便捷函数"""
    log_manager.log_api_call(endpoint, method, processing_time, status_code, error)
