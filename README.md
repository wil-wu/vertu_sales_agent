# Vertu Sales Agent - 智能客服聊天机器人

一个基于 FastAPI 和 LangGraph 构建的 AI 智能客服聊天机器人，采用 ReAct（推理+行动）代理模式。

## 🌟 核心特性

- **ReAct 智能代理架构**: 采用 ReAct 模式，结合推理和行动能力，提供智能化服务
- **多模式查询支持**: 同时处理 FAQ 知识库查询和图数据库查询，快速获取产品和多媒体信息
- **智能转接人工**: 当无法解决复杂问题时，自动转接人工客服并通过微信通知
- **对话记忆功能**: 跨多轮交互保持对话上下文，提供连贯的服务体验
- **自动路由发现**: 基于服务结构自动注册 API 路由，简化开发流程
- **Prometheus 监控**: 内置可观测性和监控系统，实时监测系统状态
- **完全容器化**: 支持 Docker 和 Docker Compose，一键部署
- **多语种适配**: 适配多语言

## 🚀 快速开始

### 前提条件

- Python 3.12 或更高版本
- UV 包管理器（推荐）或 pip
- Docker 和 Docker Compose（容器化部署时）

### 安装步骤

1. **克隆仓库**
   ```bash
   git clone <repository-url>
   cd vertu_sales_agent
   ```

2. **使用 UV 安装依赖（推荐）**
   ```bash
   uv sync
   ```

   或使用 pip：
   ```bash
   pip install -r requirements.txt
   ```

3. **配置环境变量**
   ```bash
   cp .env.example .env
   # 编辑 .env 文件，填写您的配置信息
   ```

4. **运行应用**
   ```bash
   # 开发模式运行
   uv run main.py

   # 或直接运行
   python main.py
   ```

### Docker 部署

1. **使用 Docker Compose 构建和运行**
   ```bash
   docker-compose up -d
   ```

2. **检查服务状态**
   ```bash
   curl http://localhost:8000/health
   ```

## 📋 API 文档

### 主要聊天接口

**POST** `/api/v1/react/chat`

**请求体：**
```json
{
  "message": "请问有什么产品推荐？",
  "thread_id": "unique-thread-id",
}
```

**响应体：**
```json
{
  "message": "AI 代理的智能回复内容",
  "thread_id": "unique-thread-id",
  "debug_info": []
}
```

### 健康检查接口

**GET** `/health`

返回应用的健康状态和版本信息。

### 监控指标接口

**GET** `/metrics`

Prometheus 监控指标端点（需要启用监控功能）。

## 🛠️ 系统架构

### ReAct 代理模式

ReAct（推理+行动）代理结合三个核心步骤：
- **推理分析**: 分析用户查询，理解上下文和意图
- **执行行动**: 根据推理结果选择合适的工具执行
- **观察评估**: 评估工具执行结果，优化最终响应

### 内置工具集

1. **FAQ 查询工具** (`faq_query`)
   - 查询产品知识库中的常见问题
   - 处理产品相关的常见问题和政策咨询

2. **图数据库查询工具** (`graph_query`)
   - 查询图数据库获取产品图片和视频
   - 检索产品的多媒体信息

3. **人工转接工具** (`send_wechat_notification`)
   - 将复杂问题转接给人工客服处理
   - 当 AI 无法解决时自动触发

4. **价格查询工具** (`get_product_price`)
   - 查询各平台商品价格

### 项目结构

```
vertu_sales_agent/
├── app/                        # 核心应用目录
│   ├── app.py                  # FastAPI 应用工厂
│   ├── config.py               # 全局配置
│   ├── scanner.py              # 自动路由发现
│   ├── core/                   # 核心公共模块
│   │   ├── shared.py           # 核心共享逻辑
│   │   └── middlewares.py      # 中间件
│   └── services/               # 服务模块目录
│       ├── __init__.py
│       ├── react_agent/        # ReAct 销售代理
│       │   ├── agent.py        # 核心 ReAct 代理
│       │   ├── config.py       # 代理配置
│       │   ├── deps.py         # 依赖注入
│       │   ├── prompts.py      # 系统提示词
│       │   ├── router.py       # API 路由
│       │   ├── schemas.py      # Pydantic 模型
│       │   ├── service.py      # 业务服务
│       │   ├── shared.py      # 模块内共享
│       │   ├── tools.py       # 工具实现
│       │   └── utils.py       # 工具函数
│       ├── user_agent/         # 用户侧代理
│       │   ├── agent.py
│       │   ├── config.py
│       │   ├── deps.py
│       │   ├── prompts.py
│       │   ├── router.py
│       │   ├── schemas.py
│       │   ├── shared.py
│       │   └── user_config.py
│       └── referee_agent/      # 裁判/评估代理
│           ├── agent.py
│           ├── config.py
│           ├── deps.py
│           ├── prompts.py
│           ├── router.py
│           ├── schemas.py
│           └── shared.py
├── main.py                     # 应用入口点
├── pyproject.toml              # 项目依赖（UV）
├── requirements.txt            # pip 依赖
├── env.example                 # 环境变量示例
├── Dockerfile                  # Docker 构建文件
├── docker-compose.yml          # 容器编排配置
└── docker-build.sh             # 构建脚本
```

## 🔧 开发指南

### 运行测试

```bash
# 运行测试套件
uv run pytest

# 带覆盖率运行
uv run pytest --cov=app
```

### 代码规范

```bash
# 格式化代码
uv format
```

### 添加新工具

为 ReAct 代理添加新工具：

1. 在 `app/services/react_agent/tools.py` 中定义工具函数
2. 在 `app/services/react_agent/prompts.py` 中更新提示词
3. 在代理初始化时注册新工具

### 添加新服务

新服务会被 `scanner.py` 模块自动发现：

1. 在 `app/services/` 下创建新目录
2. 添加 `router.py` 文件定义 FastAPI 路由
3. 服务将自动注册到应用中

## 🐳 Docker 部署

```bash
# 构建开发镜像
sh docker-build.sh

# 以 docker compose 运行
docker-compose up -d
```

## 📊 监控指标

应用通过 `/metrics` 端点提供 Prometheus 监控指标：

- 请求计数和持续时间
- 工具使用统计
- 错误率
- LLM API 延迟
