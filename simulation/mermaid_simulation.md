# Vertu Sales Agent Mock仿真系统流程图

## 一、系统整体架构

```mermaid
flowchart TB
    subgraph 仿真系统["🎯 Mock仿真测试系统"]
        direction TB

        subgraph 初始化层["📋 初始化配置"]
            A1[选择测试场景<br/>售后/售前/投诉]
            A2[配置用户分布<br/>20%专业+80%普通]
            A3[加载问题池<br/>jd_tm_qa_filtered.csv]
            A4[生成mock_questions.json]
        end

        subgraph 核心层["🔄 核心Agent对撞"]
            direction LR

            subgraph UserAgent["👤 User Agent<br/>Mock用户"]
                U1[Persona人格引擎]
                U2[提问生成器]
                U3[推理行动策略]
            end

            subgraph TargetBot["🤖 Target Bot<br/>待测机器人"]
                T1[ReAct Agent]
                T2[工具调用]
                T3[回答生成]
            end

            subgraph RefereeAgent["⚖️ Referee Agent<br/>裁判员"]
                R1[多维度评估]
                R2[终止条件检测]
                R3[会话记录保存]
            end
        end

        subgraph 输出层["📊 结果输出"]
            B1[datetime.json<br/>会话记录]
            B2[评估报告]
            B3[质量分析]
        end
    end

    A1 --> A2 --> A3 --> A4
    A4 --> U1

    U1 --> U2 --> U3
    U3 -->|提问| T1
    T1 --> T2 --> T3
    T3 -->|回答| R1
    R1 --> R2

    R2 -->|继续对话| U1
    R2 -->|满足终止条件| R3
    R3 --> B1 --> B2 --> B3
```

## 二、多轮对话循环流程

```mermaid
sequenceDiagram
    autonumber
    participant U as User Agent<br/>Mock用户
    participant T as Target Bot<br/>待测机器人
    participant R as Referee Agent<br/>裁判员
    participant DB as 数据存储

    Note over U: 初始化<br/>加载Persona + 问题池
    U->>U: 选择初始问题q1

    loop 最多20轮对话
        U->>T: POST /api/v1/react/chat<br/>{message: q1, thread_id}
        T->>T: ReAct推理+工具调用
        T-->>U: 返回答案a1

        U->>R: 提交对话记录<br/>(q1, a1)
        R->>R: 评估回答质量<br/>相关性/有用性/共情性
        R->>R: 检测终止条件

        alt 满足终止条件
            R-->>U: 终止信号<br/>finish_reason
            R->>DB: 保存datetime.json
            Note over R: 结束原因:<br/>- 超过20轮<br/>- 转人工<br/>- 3次无效回答
        else 继续对话
            R-->>U: 继续信号
            U->>U: 推理行动策略<br/>分析a1 → 生成q2
            Note over U: 考虑Persona特点:<br/>- 专业人士→追问细节<br/>- 焦虑客户→要求安抚<br/>- 杠精→质疑回答
        end
    end
```

## 三、提问生成策略

```mermaid
flowchart LR
    subgraph 输入["📥 输入"]
        P[Persona人格<br/>专业/小白/焦虑/杠精/双语]
        H[对话历史<br/>q1-a1, q2-a2...]
        I[意图类型<br/>咨询/投诉/闲聊]
    end

    subgraph 策略["🧠 生成策略选择"]
        direction TB
        S1[静态模板<br/>占位符填充]
        S2[动态元提示词<br/>Meta-Prompting]
        S3[Evol-Instruct演化<br/>问题复杂化]
    end

    subgraph 质量控制["✅ 质量控制"]
        Q1[Temperature=0.8-1.0<br/>增加随机性]
        Q2[语义去重<br/>Cosine<0.85]
        Q3[Red Teaming<br/>负面案例植入]
    end

    subgraph 输出["📤 输出"]
        O[生成问题qn]
    end

    P --> S2
    H --> S2
    I --> S2

    S2 --> Q1 --> Q2 --> Q3 --> O
```

## 四、User Agent内部逻辑

```mermaid
flowchart TB
    subgraph UserAgent["👤 User Agent 内部流程"]
        direction TB

        A[开始] --> B{轮数检查<br/>turn<=20?}
        B -->|是| C[选择/生成问题]
        B -->|否| Z1[结束: max_turns]

        C --> D[调用Target Bot]
        D --> E[接收回答]

        E --> F{检测转人工?}
        F -->|是| Z2[结束: human_escalation]
        F -->|否| G{检测无效回答?}

        G -->|是| H[无效计数+1]
        G -->|否| I[重置计数]

        H --> J{无效>=3?}
        J -->|是| Z3[结束: invalid_responses]
        J -->|否| K
        I --> K

        K --> L[Persona推理]
        L --> M{是否满意?}
        M -->|是| Z4[结束: satisfied]
        M -->|否| N[生成追问]
        N --> B

        Z1 & Z2 & Z3 & Z4 --> O[保存会话数据<br/>datetime.json]
    end
```

## 五、Referee Agent评估流程

```mermaid
flowchart LR
    subgraph 评估输入["📥 评估输入"]
        Q[用户问题qn]
        A[机器人回答an]
        C[对话上下文]
    end

    subgraph 评估维度["📊 多维度评分"]
        direction TB
        R1[相关性评分<br/>回答切题程度]
        R2[有用性评分<br/>问题解决程度]
        R3[共情性评分<br/>情感安抚程度]
        R4[安全性评分<br/>内容合规程度]
    end

    subgraph 终止检测["🛑 终止条件"]
        T1[轮数>=20]
        T2[检测转人工关键词]
        T3[连续3次无效回答]
        T4[用户明确结束]
    end

    subgraph 输出["📤 评估输出"]
        O1[分数记录]
        O2[终止决策]
        O3[datetime.json]
    end

    Q & A & C --> R1 & R2 & R3 & R4
    R1 & R2 & R3 & R4 --> T1 & T2 & T3 & T4
    T1 & T2 & T3 & T4 --> O1 & O2 --> O3
```

## 六、数据流向图

```mermaid
flowchart TB
    subgraph 数据源["📁 数据源"]
        CSV[jd_tm_qa_filtered.csv<br/>813个问题]
    end

    subgraph 处理层["⚙️ 处理层"]
        P1[问题池加载]
        P2[分类标记<br/>价格/技术/安全/一般]
        P3[生成mock_questions.json]
    end

    subgraph 仿真层["🎮 仿真层"]
        direction LR
        S1[User Agent<br/>Persona驱动]
        S2[Target Bot<br/>ReAct Agent]
        S3[Referee Agent<br/>质量评估]
    end

    subgraph 存储层["💾 存储层"]
        DB1[(mock_questions.json)]
        DB2[(mock_sessions/<br/>datetime.json)]
    end

    subgraph 应用层["📈 应用层"]
        A1[测试报告生成]
        A2[质量分析]
        A3[模型优化建议]
    end

    CSV --> P1 --> P2 --> P3 --> DB1
    DB1 --> S1
    S1 <-->|提问/回答| S2
    S2 --> S3
    S3 --> DB2
    DB2 --> A1 --> A2 --> A3
```

## 七、关键流程说明

### 1. 初始化流程
```mermaid
flowchart LR
    A[启动服务] --> B[加载配置<br/>env_prefix=USER_AGENT_]
    B --> C[加载问题池CSV]
    C --> D[分类&去重]
    D --> E[生成mock_questions.json]
    E --> F[初始化User Agent]
    F --> G[初始化Referee Agent]
    G --> H[等待仿真请求]
```

### 2. 单轮对话流程
```mermaid
flowchart TB
    A[User Agent<br/>生成问题] -->|POST /chat| B[Target Bot<br/>ReAct推理]
    B -->|调用工具| C[FAQ查询/图查询]
    C -->|返回结果| B
    B -->|返回答案| D[Referee Agent<br/>评估]
    D --> E{终止?}
    E -->|否| A
    E -->|是| F[保存会话]
```

---

## 流程图使用说明

1. **系统整体架构**：展示三大Agent组件和数据流向
2. **多轮对话循环**：时序图展示完整的交互过程
3. **提问生成策略**：展示从输入到输出的策略选择
4. **User Agent内部**：状态机展示终止条件判断
5. **Referee Agent评估**：展示多维度评分体系
6. **数据流向**：从原始数据到最终报告的全流程

如需修改或补充其他流程图，请告知！
