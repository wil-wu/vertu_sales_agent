# Vertu Sales Agent - 智能客服聊天机器人

一个基于 FastAPI 和 LangGraph 构建的 AI 智能客服聊天机器人，采用 ReAct（推理+行动）代理模式，专为电商平台提供智能客户支持服务。

## 🌟 核心特性

- **ReAct 智能代理架构**: 采用 ReAct 模式，结合推理和行动能力，提供智能化服务
- **多模式查询支持**: 同时处理 FAQ 知识库查询和图数据库查询，快速获取产品和多媒体信息
- **智能转接人工**: 当无法解决复杂问题时，自动转接人工客服并通过微信通知
- **对话记忆功能**: 跨多轮交互保持对话上下文，提供连贯的服务体验
- **自动路由发现**: 基于服务结构自动注册 API 路由，简化开发流程
- **Prometheus 监控**: 内置可观测性和监控系统，实时监测系统状态
- **完全容器化**: 支持 Docker 和 Docker Compose，一键部署
- **中文深度优化**: 专为中文电商客服场景设计，理解中文用户习惯

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
   uv run python main.py

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
  "query": "请问有什么产品推荐？",
  "thread_id": "unique-thread-id",
  "stream": false
}
```

**响应体：**
```json
{
  "answer": "AI 代理的智能回复内容",
  "messages": [...],
  "tools_used": ["faq_query"],
  "escalated": false
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
   - 接口地址：配置在 `FAQ_SERVICE_URL`
   - 处理产品相关的常见问题和政策咨询

2. **图数据库查询工具** (`graph_query`)
   - 查询图数据库获取产品图片和视频
   - 接口地址：配置在 `GRAPH_SERVICE_URL`
   - 检索产品的多媒体信息

3. **人工转接工具** (`human_escalation`)
   - 将复杂问题转接给人工客服处理
   - 通过微信发送通知（配置在 `HUMAN_SERVICE_URL`）
   - 当 AI 无法解决时自动触发

### 项目结构

```
vertu_sales_agent/
├── app/                      # 核心应用目录
│   ├── app.py               # FastAPI 应用工厂
│   ├── config.py            # 全局配置
│   └── scanner.py           # 自动路由发现
├── app/services/            # 服务模块目录
│   └── react_agent/         # ReAct 代理实现
│       ├── agent.py         # 核心 ReAct 代理
│       ├── tools.py         # 工具实现
│       ├── prompts.py       # 系统提示词
│       └── schemas.py       # Pydantic 模型
├── main.py                  # 应用入口点
├── pyproject.toml          # 项目依赖
├── Dockerfile              # Docker 构建文件
└── docker-compose.yml      # 容器编排配置
```

## ⚙️ 配置参数

应用使用环境变量进行配置：

| 变量名 | 描述 | 默认值 |
|----------|-------------|---------|
| `LLM_TYPE` | LLM 提供商类型 | `openai` |
| `OPENAI_API_KEY` | 大语言模型 API 密钥 | 必需配置 |
| `OPENAI_API_BASE` | LLM API 基础地址 | 可选配置 |
| `DEFAULT_LLM_MODEL` | 默认模型名称 | `moonshot-v1-128k` |
| `FAQ_SERVICE_URL` | FAQ 服务接口地址 | `http://192.168.151.84:8888/query` |
| `GRAPH_SERVICE_URL` | 图数据库服务接口 | `http://192.168.151.84:10001/nl2graph_qa` |
| `HUMAN_SERVICE_URL` | 微信通知服务接口 | 可配置 |
| `DEBUG_MODE` | 启用调试模式 | `false` |
| `CORS_ALLOW_ORIGINS` | 允许的 CORS 源 | `*` |
| `SERVER_HOST` | 服务监听地址 | `0.0.0.0` |
| `SERVER_PORT` | 服务端口 | `8000` |
| `WORKERS` | 工作进程数量 | `1` |

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
uv run black app/

# 代码检查
uv run flake8 app/

# 类型检查
uv run mypy app/
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

### 开发环境

```bash
# 构建开发镜像
docker build -t vertu-sales-agent:dev .

# 带热重载运行
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up
```

### 生产环境

```bash
# 构建生产镜像
docker build -t vertu-sales-agent:prod .

# 使用生产配置部署
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## 📊 监控指标

应用通过 `/metrics` 端点提供 Prometheus 监控指标：

- 请求计数和持续时间
- 工具使用统计
- 错误率
- LLM API 延迟

## 🔒 安全特性

- 使用 Pydantic 模型验证输入
- 支持 CORS 配置
- 基于环境变量的配置
- 无硬编码密钥

## 🤝 贡献指南

1. Fork 仓库
2. 创建功能分支
3. 提交更改
4. 推送到分支
5. 创建 Pull Request

## 📄 开源协议

本项目基于 MIT 协议开源。

## 🆘 技术支持

遇到问题或有疑问时：
- 查看 [Issues](<repository-url>/issues) 页面
- 联系开发团队

## 🏗️ 后续规划

- [ ] 多语言支持
- [ ] 语音识别集成
- [ ] 高级对话分析
- [ ] 自定义监控仪表板
- [ ] 主流电商平台集成

---

** 🎯 专注中文电商客服场景，提供智能化客户支持解决方案 **