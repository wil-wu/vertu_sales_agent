# Vertu Sales Agent Mock仿真系统流程图 (方正版)

## 一、系统整体架构

```mermaid
flowchart TB
    subgraph INIT["初始化层"]
        A1[选择测试场景]
        A2[配置用户分布]
        A3[加载CSV问题池]
        A4[生成JSON问题池]
    end

    subgraph CORE["核心Agent对撞层"]
        direction TB

        subgraph UA["User Agent"]
            U1[Persona引擎]
            U2[提问生成器]
            U3[推理策略]
        end

        subgraph TBOT["Target Bot"]
            T1[ReAct推理]
            T2[工具调用]
        end

        subgraph RA["Referee Agent"]
            R1[质量评估]
            R2[终止检测]
            R3[数据保存]
        end
    end

    subgraph OUT["输出层"]
        B1[会话记录]
        B2[评估报告]
        B3[质量分析]
    end

    A1 --> A2 --> A3 --> A4
    A4 --> U1

    U1 --> U2 --> U3
    U3 -->|提问| T1
    T1 --> T2
    T2 -->|回答| R1

    R1 --> R2
    R2 -->|继续| U1
    R2 -->|结束| R3
    R3 --> B1 --> B2 --> B3
```

## 二、多轮对话循环

```mermaid
sequenceDiagram
    participant U as User Agent
    participant T as Target Bot
    participant R as Referee Agent
    participant D as Data Store

    U->>U: 初始化Persona+问题池
    U->>U: 选择初始问题

    loop 最多20轮
        U->>T: 发送问题qn
        T->>T: ReAct推理
        T-->>U: 返回答案an

        U->>R: 提交(qn, an)
        R->>R: 多维度评估
        R->>R: 检测终止条件

        alt 满足终止条件
            R-->>U: 终止信号
            R->>D: 保存数据
        else 继续对话
            R-->>U: 继续信号
            U->>U: 生成追问qn+1
        end
    end
```

## 三、User Agent内部状态机

```mermaid
flowchart TB
    START([开始]) --> CHECK{轮数≤20?}

    CHECK -->|是| GEN[生成问题]
    CHECK -->|否| END1[结束:max_turns]

    GEN --> CALL[调用Target Bot]
    CALL --> RECV[接收回答]

    RECV --> HUMAN{转人工?}
    HUMAN -->|是| END2[结束:escalation]
    HUMAN -->|否| VALID{无效回答?}

    VALID -->|是| INC[计数+1]
    VALID -->|否| RESET[重置计数]

    INC --> CHECK3{计数≥3?}
    CHECK3 -->|是| END3[结束:invalid]
    CHECK3 -->|否| REASON[Persona推理]

    RESET --> REASON

    REASON --> SATISFY{满意?}
    SATISFY -->|是| END4[结束:satisfied]
    SATISFY -->|否| FOLLOW[生成追问]

    FOLLOW --> CHECK

    END1 & END2 & END3 & END4 --> SAVE[保存会话]
    SAVE --> STOP([停止])
```

## 四、提问生成策略矩阵

```mermaid
flowchart LR
    subgraph IN["输入"]
        P[Persona]
        H[历史记录]
        I[意图类型]
    end

    subgraph STRATEGY["策略选择"]
        S1[静态模板]
        S2[动态元提示词]
        S3[Evol-Instruct演化]
    end

    subgraph QC["质量控制"]
        Q1[Temperature]
        Q2[语义去重]
        Q3[Red Teaming]
    end

    subgraph OUT["输出"]
        O[生成问题]
    end

    P & H & I --> S2
    S2 --> Q1 --> Q2 --> Q3 --> O
```

## 五、Referee Agent评估流程

```mermaid
flowchart TB
    subgraph INPUT["评估输入"]
        Q[用户问题]
        A[机器人回答]
        C[对话上下文]
    end

    subgraph EVAL["评估维度"]
        E1[相关性]
        E2[有用性]
        E3[共情性]
        E4[安全性]
    end

    subgraph TERM["终止检测"]
        T1[轮数≥20]
        T2[转人工]
        T3[3次无效]
        T4[用户结束]
    end

    subgraph OUTPUT["评估输出"]
        S[评分记录]
        D[终止决策]
        F[保存文件]
    end

    Q & A & C --> E1 & E2 & E3 & E4
    E1 & E2 & E3 & E4 --> T1 & T2 & T3 & T4
    T1 & T2 & T3 & T4 --> S --> D --> F
```

## 六、数据流向图

```mermaid
flowchart LR
    subgraph SOURCE["数据源"]
        CSV[CSV文件]
    end

    subgraph PROCESS["处理层"]
        P1[加载问题池]
        P2[分类标记]
        P3[生成JSON]
    end

    subgraph SIMULATION["仿真层"]
        S1[User Agent]
        S2[Target Bot]
        S3[Referee Agent]
    end

    subgraph STORAGE["存储层"]
        DB1[问题池JSON]
        DB2[会话记录]
    end

    subgraph APPLICATION["应用层"]
        A1[测试报告]
        A2[质量分析]
        A3[优化建议]
    end

    CSV --> P1 --> P2 --> P3 --> DB1
    DB1 --> S1
    S1 <--> S2
    S2 --> S3
    S3 --> DB2
    DB2 --> A1 --> A2 --> A3
```

## 七、完整工作流程

```mermaid
flowchart TB
    subgraph STEP1["步骤1:初始化"]
        S1A[读取配置]
        S1B[加载CSV]
        S1C[生成问题池]
    end

    subgraph STEP2["步骤2:开始仿真"]
        S2A[接收请求]
        S2B[选择Persona]
        S2C[选择初始问题]
    end

    subgraph STEP3["步骤3:对话循环"]
        S3A[生成问题]
        S3B[调用Target Bot]
        S3C[评估回答]
        S3D{终止?}
    end

    subgraph STEP4["步骤4:结束处理"]
        S4A[保存会话]
        S4B[生成报告]
        S4C[返回结果]
    end

    S1A --> S1B --> S1C
    S1C --> S2A --> S2B --> S2C
    S2C --> S3A --> S3B --> S3C --> S3D

    S3D -->|否| S3A
    S3D -->|是| S4A --> S4B --> S4C
```

## 八、组件交互图

```mermaid
flowchart LR
    subgraph CLIENT["客户端"]
        C[API请求]
    end

    subgraph SERVER["服务端"]
        direction TB

        subgraph ROU["路由层"]
            R1[/start接口/]
            R2[/session接口/]
        end

        subgraph SVC["服务层"]
            SVC1[UserAgent]
            SVC2[RefereeAgent]
        end

        subgraph DEP["依赖层"]
            D1[(问题池)]
            D2[(配置)]
        end
    end

    subgraph TARGET["目标系统"]
        T[React Agent]
    end

    subgraph FILE["文件系统"]
        F1[(mock_questions.json)]
        F2[(datetime.json)]
    end

    C --> R1 & R2
    R1 --> SVC1
    SVC1 --> D1 & D2
    SVC1 <--> T
    SVC1 --> SVC2
    SVC2 --> F2
    D1 --> F1
```

## 九、关键决策点

```mermaid
flowchart TB
    D1{选择Persona?} -->|专业| P1[technical]
    D1 -->|小白| P2[simple]
    D1 -->|焦虑| P3[worried]
    D1 -->|杠精| P4[challenging]
    D1 -->|双语| P5[mixed]

    P1 & P2 & P3 & P4 & P5 --> D2{终止条件?}

    D2 -->|轮数≥20| E1[max_turns]
    D2 -->|转人工| E2[escalation]
    D2 -->|3次无效| E3[invalid]
    D2 -->|用户满意| E4[satisfied]

    E1 & E2 & E3 & E4 --> D3{评估结果?}

    D3 -->|优秀| R1[通过]
    D3 -->|良好| R2[改进]
    D3 -->|差| R3[重构]
```

## 十、部署架构

```mermaid
flowchart TB
    subgraph USER["用户"]
        U[浏览器/API客户端]
    end

    subgraph APP["应用服务"]
        direction TB

        subgraph FASTAPI["FastAPI服务"]
            F1[Router]
            F2[Service]
            F3[Agent]
        end

        subgraph AGENTS["Agent组件"]
            A1[UserAgent]
            A2[RefereeAgent]
            A3[TargetBot]
        end
    end

    subgraph DATA["数据存储"]
        D1[(CSV)]
        D2[(JSON池)]
        D3[(会话记录)]
    end

    subgraph EXTERNAL["外部服务"]
        E1[LLM API]
    end

    U --> F1
    F1 --> F2 --> F3
    F3 --> A1 & A2 & A3
    A1 & A2 --> D2 & D3
    A1 & A2 --> E1
    A3 --> D1
```

---

## 设计说明

本版本流程图优化了以下方面：

1. **布局方正**: 使用TB/LR方向控制，避免斜向连接
2. **边长控制**: 模块化设计，减少长距离连接
3. **对齐整齐**: 使用subgraph分组，保持视觉整齐
4. **逻辑清晰**: 每个流程图专注单一职责
5. **可读性强**: 标签简洁，避免过长文字
