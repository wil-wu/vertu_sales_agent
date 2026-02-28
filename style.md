# Vertu Sales Agent — 项目代码风格说明

写新代码或改老代码时，请按这份文档来，保持风格一致。需要调整规则时，直接改这个文件即可。

---

## 1. 项目简介

- **技术栈**：FastAPI + LangChain/LangGraph，Python ≥3.12。
- **做什么的**：ReAct 风格智能体服务，自动扫描并注册各业务服务的 API，带监控指标、日志、CORS、中间件等。
- **包管理**：用 `uv`，锁文件是 `uv.lock`，依赖写在 `pyproject.toml`。

---

## 2. 目录结构

```
vertu_sales_agent/
├── main.py                 # 入口：create_app()、uvicorn.run()
├── app/
│   ├── app.py              # create_app()、生命周期、中间件、路由注册
│   ├── config.py           # 全局配置 GlobalSettings（pydantic-settings）
│   ├── scanner.py          # RouterScanner：自动发现 app.services.*.router
│   └── core/
│       ├── middlewares.py  # 自定义中间件（如 RequestLoggingMiddleware）
│       └── shared.py       # 全局共享实例（如 httpx_client）
└── app/services/
    └── <服务名>/            # 每个服务一个文件夹
        ├── __init__.py     # 空或极简
        ├── router.py       # 必须定义 router: APIRouter
        ├── config.py       # 本服务配置（带 env_prefix）
        ├── deps.py         # FastAPI 依赖注入（如 get_react_agent）
        ├── agent.py        # 业务/Agent 逻辑（有的话）
        ├── prompts.py      # 提示词常量（如 SYSTEM_PROMPT）
        ├── schemas.py      # 请求/响应 Pydantic 模型
        ├── shared.py       # 本服务内共享实例（如 chat_model）
        └── tools.py        # LangChain 工具 + TOOLS 列表（有的话）
```

- **新增服务**：在 `app/services/<服务名>/` 下新建目录，至少要有 `router.py` 并导出 `router`，扫描器会自动发现。
- **配置归属**：全局配置在 `app/config.py`；某个服务自己的配置在 `app/services/<服务名>/config.py`，用 `env_prefix`（如 `REACT_AGENT_`）区分环境变量。

---

## 3. 代码风格

### 3.1 通用

- **Python**：3.12+，用新式类型注解：`list[str]`、`dict[str, Any]`、`Self` 等。
- **格式与检查**：用 **Ruff**（项目里没有单独配置文件，按 Ruff 默认 + 下面约定即可）。
- **行宽**：以易读为准，太长就换行。
- **文档字符串**：面向业务/用户的说明用**中文**；纯技术/API 用英文也行。用 `"""..."""`，函数/方法可写 `Args:`、`Returns:`。

### 3.2 命名

| 类型           | 规范        | 示例                         |
|----------------|-------------|------------------------------|
| 模块/包        | snake_case  | `react_agent`、`config.py`   |
| 类             | PascalCase  | `ReActAgent`、`GlobalSettings` |
| 函数/方法      | snake_case  | `create_app`、`get_react_agent` |
| 常量           | UPPER_SNAKE | `SYSTEM_PROMPT`、`TOOLS`     |
| 变量           | snake_case  | `request_info`、`chat_model` |
| 异步函数       | 有 I/O 用 async | `async def chat`、`async def dispatch` |

### 3.3 导入顺序

1. 标准库（如 `logging`、`uuid`、`pathlib`）。
2. 第三方（如 `fastapi`、`pydantic`、`langchain_*`）。
3. 本项目：应用级用 `from app.xxx`，包内用 `from .xxx`。

```python
import logging
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.config import settings
from .deps import get_react_agent
from .schemas import ReactAgentRequest, ReactAgentResponse
```

- 每组之间空一行，不要留未使用的导入。

### 3.4 日志

- 用标准库，按模块名取 logger：

```python
import logging
logger = logging.getLogger(__name__)
```

- 按需用 `logger.info`、`logger.warning`、`logger.error`、`logger.debug`。工具/请求边界可加简短前缀（如 `--- [TOOL] 查询 FAQ: ... ---`）。
- **不要打日志打出密钥、Token、API Key**。中间件已对 `authorization`、`cookie`、`x-api-key` 等做脱敏。

---

## 4. 配置

### 4.1 全局配置（`app/config.py`）

- 一个类：`GlobalSettings(BaseSettings)`。
- `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")`。
- 字段都用 `Field(default=..., description="...")`，description 可中文可英文。
- 导出一个单例：`settings = GlobalSettings()`。
- 全局相关（host、port、CORS、监控、debug、日志级别等）都从 `settings` 读。

### 4.2 服务级配置（`app/services/<服务名>/config.py`）

- 每个服务一个配置类，如 `ReactAgentSettings(BaseSettings)`。
- 用 `env_prefix` 区分环境变量（如 `REACT_AGENT_`）。
- 同样用 `Field(default=..., description="...")`、`extra="ignore"`。
- 导出一个单例：`react_agent_settings = ReactAgentSettings()`（或 `<服务名>_settings`）。

---

## 5. FastAPI 约定

### 5.1 应用创建（`app/app.py`）

- `create_app() -> FastAPI`：创建 app，设 title/version/description、**lifespan**，然后依次：
  1. 加 CORS 中间件。
  2. 加自定义中间件（如请求日志）。
  3. 若 `settings.enable_metrics` 为真，加 Prometheus，排除 `/metrics`、`/health`。
  4. `RouterScanner(app).scan_and_register()` 注册各服务路由。
  5. 注册根路由：`/`、`/health`、`/routes`（仅 debug 时可用）。
- **Lifespan**：用 `@asynccontextmanager async def lifespan(app):`，启动时（如打版本日志）、关闭时（如 `await httpx_client.aclose()`）。

### 5.2 服务路由（`app/services/<服务名>/router.py`）

- 定义一个 `APIRouter`，带 `prefix` 和 `tags`：

```python
router = APIRouter(
    prefix="/api/v1/react",
    tags=["React Agent"],
)
```

- 接口函数：`async def`，请求体/返回值写类型，用 `Depends()` 做依赖注入。
- 返回结构化 body 的路由要设 `response_model`。

```python
@router.post("/chat", response_model=ReactAgentResponse)
async def chat(
    request: ReactAgentRequest,
    react_agent: ReActAgent = Depends(get_react_agent),
) -> ReactAgentResponse:
    message = await react_agent.arun(request.message, request.thread_id)
    return {
        "message": message,
        "thread_id": request.thread_id,
    }
```

- 直接返回和 `response_model` 对应的 dict 即可，Pydantic 会校验。

### 5.3 依赖注入（`deps.py`）

- 每个可注入对象一个函数，返回具体类型（如 `ReActAgent`）。除非要收尾逻辑，否则不用 `yield`。
- 在 router 里用 `Depends(get_xxx)` 注入。

```python
def get_react_agent() -> ReActAgent:
    return ReActAgent(
        chat_model=chat_model,
        tools=TOOLS,
        system_prompt=SYSTEM_PROMPT,
    )
```

---

## 6. Pydantic 模型

### 6.1 请求/响应（`schemas.py`）

- 用 `BaseModel` + `Field(..., description="...")` 定义 API 契约。
- 需要默认值（如 `thread_id`）时用 `default_factory`（如 `default_factory=lambda: str(uuid.uuid4())`）。
- 路由参数里用明确的请求/响应模型（如 `ReactAgentRequest`、`ReactAgentResponse`），不要裸 dict。

---

## 7. LangChain / LangGraph

### 7.1 LLM 客户端（`shared.py`）

- 用本服务的 config 创建（如 `ChatOpenAI(base_url=..., api_key=..., model=...)`），导出一个实例（如 `chat_model`）供本服务用。

### 7.2 工具（`tools.py`）

- 有 I/O 的用 `@tool` + async：`async def faq_query(query: str): ...`。
- 工具的 docstring 会被 Agent 用到，写清楚；面向中文产品就写中文。
- 工具收集到一个列表：`TOOLS = [faq_query, graph_query, escalate_to_human]`。
- HTTP 用 `app.core.shared` 里的 `httpx_client`；URL、密钥等从本服务 `config` 读。

### 7.3 Agent / 图（`agent.py`）

- 图的构建和调用封装在一个类里（如 `ReActAgent`）。需要同步/异步都暴露时，提供 `run` 和 `arun`。
- 用 LangGraph 的 `StateGraph(MessagesState)`、`ToolNode`、条件边、checkpointer（如 `MemorySaver()`）。
- 系统提示里需要动态内容（如 `current_time`）在 agent 节点里拼，不要在 router 里拼。
- Agent 用单例也可以（当前 `ReActAgent` 就是这样）；否则通过 `deps.py` 注入。

### 7.4 提示词（`prompts.py`）

- 大段提示词放在模块级常量（如 `SYSTEM_PROMPT = """..."""`）。占位符用 `{current_time}` 这种，在 agent 里 `.format(...)` 填入。

---

## 8. 中间件与共享资源

### 8.1 中间件

- 类继承 `BaseHTTPMiddleware`，实现 `async def dispatch(self, request, call_next) -> Response`。
- 构造函数接收 `app` 和可选参数（如 `log_request_body`、`exclude_paths`），并调用 `super().__init__(app)`。
- 打日志时跳过健康检查、指标等路径；敏感请求头先脱敏再打。

### 8.2 共享资源（`app/core/shared.py`）

- 全局 HTTP 客户端：`httpx.AsyncClient()` 作为模块级实例（如 `httpx_client`），在应用 lifespan 关闭时调用 `aclose()`。

---

## 9. 启动与运行

- **入口**：`main.py` 里导入 `create_app` 和 `settings`，用 uvicorn 跑，参数来自 `settings`（host、port、reload=debug、log_level）。
- **Docker**：`uv sync --locked` 安装，`uv run main.py` 启动。Python 3.12；Dockerfile 里时区设为 `Asia/Shanghai` 是刻意保留的。

---

## 10. 新代码自检清单

- [ ] 导入：标准库 → 第三方 → 本项目的 `app.*` / `.*`，顺序一致。
- [ ] 类型：函数参数和返回值都写类型；用 `list[str]`、`dict[str, Any]` 等。
- [ ] 配置：全局在 `app/config.py`，服务专属在 `app/services/<名>/config.py` 并设 `env_prefix`。
- [ ] 路由：`app/services/<名>/router.py` 里定义 `router`，带 `prefix`、`tags`；接口用 `async def`，需要时用 `Depends` 和 `response_model`。
- [ ] 模型：在 `schemas.py` 里用 Pydantic + `Field(..., description="...")`。
- [ ] 日志：`logger = logging.getLogger(__name__)`；不打密钥。
- [ ] 文档字符串：面向业务的用中文；需要时写 Args/Returns。
- [ ] 新服务：在 `app/services/<名>/` 下建目录，至少要有 `router.py` 并导出 `router`。

以后生成或重构代码时，按这份说明来即可；若要改规范，直接编辑本文件。
