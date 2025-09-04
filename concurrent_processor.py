# -*- coding: utf-8 -*-
"""
并发处理模块
支持大批量PDF文件的并发处理，包含速率限制和智能调度
"""

import asyncio
import time
import logging
from typing import List, Dict, Any, Callable, Optional
from dataclasses import dataclass
from collections import deque
import threading
from concurrent.futures import ThreadPoolExecutor
import os

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class RateLimitConfig:
    """速率限制配置"""
    rpm: int = 1200  # 每分钟请求数
    tpm: int = 5000000  # 每分钟token数
    max_concurrent: int = 20  # 最大并发数
    batch_size: int = 10  # 批次大小
    retry_attempts: int = 3  # 重试次数
    retry_delay: float = 1.0  # 重试延迟(秒)

class RateLimiter:
    """速率限制器"""
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.request_times = deque()
        self.token_usage = deque()
        self.lock = threading.Lock()
        
        # 计算安全的请求间隔
        self.min_request_interval = 60.0 / config.rpm  # 秒
        self.safe_request_interval = self.min_request_interval * 1.2  # 增加20%安全边距
        
    def can_make_request(self, estimated_tokens: int = 1000) -> bool:
        """检查是否可以发起请求"""
        with self.lock:
            current_time = time.time()
            
            # 清理过期的请求记录（1分钟前的）
            while self.request_times and current_time - self.request_times[0] > 60:
                self.request_times.popleft()
            
            while self.token_usage and current_time - self.token_usage[0][0] > 60:
                self.token_usage.popleft()
            
            # 检查RPM限制
            if len(self.request_times) >= self.config.rpm * 0.9:  # 90%安全边距
                return False
            
            # 检查TPM限制
            current_tokens = sum(usage[1] for usage in self.token_usage)
            if current_tokens + estimated_tokens > self.config.tpm * 0.9:  # 90%安全边距
                return False
            
            return True
    
    def record_request(self, tokens_used: int = 1000):
        """记录请求"""
        with self.lock:
            current_time = time.time()
            self.request_times.append(current_time)
            self.token_usage.append((current_time, tokens_used))
    
    async def wait_for_rate_limit(self, estimated_tokens: int = 1000):
        """等待直到可以发起请求"""
        while not self.can_make_request(estimated_tokens):
            await asyncio.sleep(0.1)
        
        # 额外等待以确保请求间隔
        if self.request_times:
            time_since_last = time.time() - self.request_times[-1]
            if time_since_last < self.safe_request_interval:
                wait_time = self.safe_request_interval - time_since_last
                await asyncio.sleep(wait_time)

class ConcurrentProcessor:
    """并发处理器"""
    
    def __init__(self, config: RateLimitConfig = None):
        self.config = config or RateLimitConfig()
        self.rate_limiter = RateLimiter(self.config)
        self.semaphore = asyncio.Semaphore(self.config.max_concurrent)
        
    async def process_single_file(self, file_path: str, process_func: Callable, mode: str) -> Dict[str, Any]:
        """处理单个文件"""
        async with self.semaphore:
            for attempt in range(self.config.retry_attempts):
                try:
                    # 等待速率限制
                    await self.rate_limiter.wait_for_rate_limit()
                    
                    # 记录请求开始
                    start_time = time.time()
                    self.rate_limiter.record_request()
                    
                    # 执行处理
                    result = await process_func(file_path, mode)
                    
                    # 计算处理时间
                    processing_time = time.time() - start_time
                    
                    # 添加处理信息
                    if isinstance(result, dict):
                        result['processing_time'] = round(processing_time, 2)
                        result['attempt'] = attempt + 1
                    
                    logger.info(f"成功处理文件: {os.path.basename(file_path)} (耗时: {processing_time:.2f}s)")
                    return result
                    
                except Exception as e:
                    error_msg = str(e)
                    logger.warning(f"处理文件失败 (尝试 {attempt + 1}/{self.config.retry_attempts}): {os.path.basename(file_path)} - {error_msg}")

                    if attempt < self.config.retry_attempts - 1:
                        # 指数退避重试
                        wait_time = self.config.retry_delay * (2 ** attempt)
                        logger.info(f"等待 {wait_time:.1f} 秒后重试...")
                        await asyncio.sleep(wait_time)
                    else:
                        # 最后一次尝试失败，返回详细错误结果
                        filename = os.path.basename(file_path)
                        # 去掉.pdf扩展名
                        if filename.lower().endswith('.pdf'):
                            filename = filename[:-4]

                        error_details = {
                            'file': file_path,
                            'filename': filename,
                            'error': error_msg,
                            'status': 'failed',
                            'attempts': self.config.retry_attempts,
                            'error_type': type(e).__name__,
                            'processing_time': time.time() - start_time
                        }

                        # 提供更具体的错误分类
                        if "API密钥" in error_msg or "401" in error_msg:
                            error_details['error_category'] = 'auth'
                        elif "频率过高" in error_msg or "429" in error_msg:
                            error_details['error_category'] = 'rate_limit'
                        elif "超时" in error_msg:
                            error_details['error_category'] = 'timeout'
                        elif "网络" in error_msg:
                            error_details['error_category'] = 'network'
                        else:
                            error_details['error_category'] = 'processing'

                        return error_details

    async def process_single_file_with_index(self, file_path: str, process_func: Callable, mode: str, original_index: int) -> Dict[str, Any]:
        """处理单个文件并保留原始索引"""
        result = await self.process_single_file(file_path, process_func, mode)

        # 添加原始索引到结果中
        if isinstance(result, dict):
            result['_original_index'] = original_index
            result['_upload_order'] = original_index + 1  # 从1开始的上传顺序

        return result

    async def process_batch(self, file_paths: List[str], process_func: Callable, mode: str,
                          progress_callback: Optional[Callable] = None) -> List[Dict[str, Any]]:
        """批量处理文件 - 全并发模式"""
        total_files = len(file_paths)
        logger.info(f"开始全并发处理 {total_files} 个文件，模式: {mode}")

        # 创建所有任务，全部并发执行，并保存原始索引
        tasks = []
        for i, file_path in enumerate(file_paths):
            task = self.process_single_file_with_index(file_path, process_func, mode, i)
            tasks.append(task)

        logger.info(f"启动 {len(tasks)} 个并发任务...")

        # 全部并发执行
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理异常结果
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                filename = os.path.basename(file_paths[i])
                # 去掉.pdf扩展名
                if filename.lower().endswith('.pdf'):
                    filename = filename[:-4]

                results[i] = {
                    'file': file_paths[i],
                    'filename': filename,
                    'error': str(result),
                    'status': 'failed',
                    '_original_index': i,
                    '_upload_order': i + 1
                }
        
        # 按照原始索引重新排序，确保返回顺序与上传顺序一致
        results.sort(key=lambda x: x.get('_original_index', 0))

        # 统计结果
        successful = sum(1 for r in results if r.get('status') != 'failed' and 'error' not in r)
        failed = len(results) - successful

        logger.info(f"全并发处理完成: 成功 {successful}, 失败 {failed}, 总计 {total_files}")

        # 最终进度回调
        if progress_callback:
            await progress_callback(100, f"处理完成: 成功 {successful}, 失败 {failed}")

        return results
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """获取处理统计信息"""
        with self.rate_limiter.lock:
            current_time = time.time()
            
            # 计算最近1分钟的请求数
            recent_requests = sum(1 for t in self.rate_limiter.request_times 
                                if current_time - t <= 60)
            
            # 计算最近1分钟的token使用量
            recent_tokens = sum(usage[1] for usage in self.rate_limiter.token_usage 
                              if current_time - usage[0] <= 60)
            
            return {
                'recent_requests_per_minute': recent_requests,
                'recent_tokens_per_minute': recent_tokens,
                'rpm_limit': self.config.rpm,
                'tpm_limit': self.config.tpm,
                'rpm_usage_percent': (recent_requests / self.config.rpm) * 100,
                'tpm_usage_percent': (recent_tokens / self.config.tpm) * 100,
                'max_concurrent': self.config.max_concurrent,
                'current_concurrent': self.config.max_concurrent - self.semaphore._value
            }

# 全局处理器实例
_global_processor = None

def get_global_processor() -> ConcurrentProcessor:
    """获取全局处理器实例"""
    global _global_processor
    if _global_processor is None:
        # 针对qwen-flash模型优化的配置 - 全并发模式
        config = RateLimitConfig(
            rpm=1200,  # 提高RPM限制
            tpm=5000000,  # 提高TPM限制
            max_concurrent=100,  # 合理的并发数，避免资源耗尽
            batch_size=50,  # 合理的批次大小
            retry_attempts=3,
            retry_delay=1.0
        )
        _global_processor = ConcurrentProcessor(config)
    return _global_processor

def reset_global_processor():
    """重置全局处理器（用于测试）"""
    global _global_processor
    _global_processor = None
