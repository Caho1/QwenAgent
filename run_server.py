# -*- coding: utf-8 -*-
"""
PDF元数据提取系统启动脚本
"""

import os
import sys
import argparse
from pathlib import Path

def check_dependencies():
    """检查依赖包"""
    required_packages = {
        'Flask': 'flask',
        'Flask-CORS': 'flask_cors',
        'pandas': 'pandas',
        'openpyxl': 'openpyxl',
        'PyMuPDF': 'fitz',
        'aiohttp': 'aiohttp',
        'regex': 'regex'
    }

    missing_packages = []
    for pip_name, import_name in required_packages.items():
        try:
            __import__(import_name)
        except ImportError:
            missing_packages.append(pip_name)

    if missing_packages:
        print("❌ 缺少以下依赖包:")
        for package in missing_packages:
            print(f"   - {package}")
        print("\n请运行以下命令安装依赖:")
        print(f"pip install {' '.join(missing_packages)}")
        return False

    return True

def check_files():
    """检查必要文件"""
    required_files = [
        'Metadata.py',
        'templates/PDF.html',
        'routes.py',
        'data_processor.py'
    ]
    
    missing_files = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
    
    if missing_files:
        print("❌ 缺少以下必要文件:")
        for file_path in missing_files:
            print(f"   - {file_path}")
        return False
    
    return True

def create_directories():
    """创建必要目录"""
    directories = ['uploads', 'results', 'templates']
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        print(f"📁 创建目录: {directory}")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='PDF元数据提取系统')
    parser.add_argument('--host', default='0.0.0.0', help='服务器地址 (默认: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=5000, help='端口号 (默认: 5000)')
    parser.add_argument('--debug', action='store_true', help='启用调试模式')
    parser.add_argument('--check-only', action='store_true', help='仅检查环境，不启动服务')
    
    args = parser.parse_args()
    
    print("🚀 PDF元数据提取系统")
    print("=" * 50)
    
    # 环境检查
    print("🔍 检查运行环境...")
    
    if not check_dependencies():
        sys.exit(1)
    
    if not check_files():
        sys.exit(1)
    
    print("✅ 依赖检查通过")
    
    # 创建目录
    print("\n📁 创建必要目录...")
    create_directories()
    
    if args.check_only:
        print("\n✅ 环境检查完成，系统就绪!")
        return
    
    # 启动服务器
    print(f"\n🌐 启动服务器...")
    print(f"   地址: http://{args.host}:{args.port}")
    print(f"   调试模式: {'开启' if args.debug else '关闭'}")
    print("\n按 Ctrl+C 停止服务器")
    print("=" * 50)
    
    try:
        # 导入并启动Flask应用
        from routes import app
        app.run(
            host=args.host,
            port=args.port,
            debug=args.debug
        )
    except KeyboardInterrupt:
        print("\n\n👋 服务器已停止")
    except Exception as e:
        print(f"\n❌ 启动失败: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
