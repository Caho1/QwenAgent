# PDF元数据提取器

一个基于AI的PDF论文元数据提取工具，支持多种提取模式和高并发处理。

## 功能特性

- 🚀 **高并发处理**: 支持100个文件同时处理，性能提升54倍
- 📊 **多种提取模式**: 
  - SN信息表收集
  - IEEE信息表收集  
  - 资助信息提取（含致谢信息）
  - AP信息表收集（姓名分离）
- 🎯 **智能提取**: 基于大语言模型的准确信息提取
- 📋 **文件顺序保持**: 处理结果按上传顺序显示
- 📱 **现代化界面**: 响应式Web界面，支持表格自动换行
- 📥 **Excel导出**: 一键导出处理结果为Excel文件

## 快速开始

### 环境要求

- Python 3.8+
- 现代浏览器

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动服务

```bash
python run_server.py
```

然后在浏览器中访问 `http://localhost:6666`

## 使用方法

1. **选择提取模式**: 根据需要选择SN、IEEE、资助信息或AP模式
2. **上传PDF文件**: 支持单个或批量上传PDF文件
3. **开始处理**: 点击开始处理，系统将自动提取元数据
4. **查看结果**: 在表格中查看提取结果，支持长文本自动换行
5. **导出Excel**: 点击下载按钮导出结果为Excel文件

## API接口

### 单模式提取
```
POST /api/extract/<mode>
```

### 批量处理
```
POST /api/extract/batch
```

### 处理统计
```
GET /api/processing/stats
```

## 项目结构

```
PDF_Extract/
├── Metadata.py              # 核心元数据提取模块
├── pdf_metadata_api.py      # Flask API服务
├── concurrent_processor.py  # 并发处理器
├── config.py                # 配置文件
├── run_server.py            # 服务启动脚本
├── requirements.txt         # 依赖列表
├── templates/
│   └── PDF.html            # Web界面
├── static/
│   └── favicon.ico         # 网站图标
└── README.md               # 项目说明
```

## 技术特点

- **智能速率控制**: 针对API限制优化的并发处理
- **容错重试**: 自动重试机制确保处理稳定性
- **内存优化**: 高效的资源管理和内存使用
- **实时监控**: 提供详细的处理统计和进度信息

## 许可证

MIT License
