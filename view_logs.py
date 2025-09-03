# -*- coding: utf-8 -*-
"""
日志查看脚本
用于在后台查看和管理日志文件
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import argparse

def list_log_files(log_dir="log"):
    """列出所有日志文件"""
    log_path = Path(log_dir)
    if not log_path.exists():
        print(f"❌ 日志目录 {log_dir} 不存在")
        return
    
    log_files = list(log_path.glob("*.log"))
    if not log_files:
        print(f"📁 日志目录 {log_dir} 中没有日志文件")
        return
    
    print(f"📁 日志目录: {log_dir}")
    print(f"📊 共找到 {len(log_files)} 个日志文件")
    print("=" * 80)
    
    # 按修改时间排序
    log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    
    for i, log_file in enumerate(log_files, 1):
        stat = log_file.stat()
        size_mb = stat.st_size / (1024 * 1024)
        mod_time = datetime.fromtimestamp(stat.st_mtime)
        
        print(f"{i:2d}. {log_file.name}")
        print(f"    大小: {size_mb:.2f} MB")
        print(f"    修改时间: {mod_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print()

def view_log_file(log_dir="log", filename=None, lines=50):
    """查看指定日志文件的内容"""
    log_path = Path(log_dir) / filename
    if not log_path.exists():
        print(f"❌ 日志文件 {filename} 不存在")
        return
    
    print(f"📖 查看日志文件: {filename}")
    print(f"📁 文件路径: {log_path.absolute()}")
    print(f"📊 文件大小: {log_path.stat().st_size / 1024:.2f} KB")
    print("=" * 80)
    
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            # 读取最后N行
            all_lines = f.readlines()
            if len(all_lines) <= lines:
                print("".join(all_lines))
            else:
                print(f"... (显示最后 {lines} 行，共 {len(all_lines)} 行) ...")
                print("=" * 40)
                print("".join(all_lines[-lines:]))
    except Exception as e:
        print(f"❌ 读取日志文件失败: {e}")

def search_logs(log_dir="log", keyword=None, ip=None):
    """搜索日志内容"""
    log_path = Path(log_dir)
    if not log_path.exists():
        print(f"❌ 日志目录 {log_dir} 不存在")
        return
    
    log_files = list(log_path.glob("*.log"))
    if not log_files:
        print(f"📁 日志目录 {log_dir} 中没有日志文件")
        return
    
    print(f"🔍 搜索日志文件...")
    if keyword:
        print(f"关键词: {keyword}")
    if ip:
        print(f"IP地址: {ip}")
    print("=" * 80)
    
    found_count = 0
    for log_file in log_files:
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()
                matches = []
                
                for line_num, line in enumerate(content.split('\n'), 1):
                    if keyword and keyword.lower() in line.lower():
                        matches.append((line_num, line))
                    if ip and ip in line:
                        matches.append((line_num, line))
                
                if matches:
                    found_count += 1
                    print(f"📄 {log_file.name} (找到 {len(matches)} 个匹配)")
                    for line_num, line in matches[:10]:  # 最多显示10个匹配
                        print(f"  第{line_num:4d}行: {line.strip()}")
                    if len(matches) > 10:
                        print(f"  ... 还有 {len(matches) - 10} 个匹配")
                    print()
                    
        except Exception as e:
            print(f"❌ 读取日志文件 {log_file.name} 失败: {e}")
    
    if found_count == 0:
        print("🔍 未找到匹配的日志内容")

def cleanup_old_logs(log_dir="log", days=30):
    """清理旧日志文件"""
    log_path = Path(log_dir)
    if not log_path.exists():
        print(f"❌ 日志目录 {log_dir} 不存在")
        return
    
    import time
    current_time = time.time()
    cutoff_time = current_time - (days * 24 * 60 * 60)
    
    log_files = list(log_path.glob("*.log"))
    old_files = [f for f in log_files if f.stat().st_mtime < cutoff_time]
    
    if not old_files:
        print(f"✅ 没有{days}天前的旧日志文件需要清理")
        return
    
    print(f"🗑️  清理 {days} 天前的旧日志文件...")
    print(f"📊 找到 {len(old_files)} 个旧文件")
    
    deleted_count = 0
    for log_file in old_files:
        try:
            mod_time = datetime.fromtimestamp(log_file.stat().st_mtime)
            print(f"删除: {log_file.name} (修改时间: {mod_time.strftime('%Y-%m-%d %H:%M:%S')})")
            log_file.unlink()
            deleted_count += 1
        except Exception as e:
            print(f"❌ 删除文件 {log_file.name} 失败: {e}")
    
    print(f"✅ 成功清理 {deleted_count} 个旧日志文件")

def main():
    parser = argparse.ArgumentParser(description="日志查看和管理工具")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有日志文件")
    parser.add_argument("--view", "-v", help="查看指定日志文件")
    parser.add_argument("--lines", "-n", type=int, default=50, help="显示的行数 (默认: 50)")
    parser.add_argument("--search", "-s", help="搜索关键词")
    parser.add_argument("--ip", help="搜索指定IP地址")
    parser.add_argument("--cleanup", "-c", type=int, metavar="DAYS", help="清理指定天数前的旧日志")
    parser.add_argument("--dir", "-d", default="log", help="日志目录 (默认: log)")
    
    args = parser.parse_args()
    
    if not any([args.list, args.view, args.search, args.ip, args.cleanup]):
        # 默认显示帮助
        parser.print_help()
        return
    
    if args.list:
        list_log_files(args.dir)
    
    if args.view:
        view_log_file(args.dir, args.view, args.lines)
    
    if args.search or args.ip:
        search_logs(args.dir, args.search, args.ip)
    
    if args.cleanup:
        cleanup_old_logs(args.dir, args.cleanup)

if __name__ == "__main__":
    main()
