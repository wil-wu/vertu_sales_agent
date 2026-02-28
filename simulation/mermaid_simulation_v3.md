# Vertu Sales Agent Mock仿真系统流程图 (紧凑正方形版)

## 一、系统核心架构

```mermaid
flowchart TB
    subgraph IN["输入"]
        I1[CSV问题池]
        I2[Persona配置]
    end

    subgraph CORE["核心处理"]
        direction LR
        U[User Agent] <-->|问答| T[Target Bot]
        T --> R[Referee Agent]
        R -->|评估| U
    end

    subgraph OUT["输出"]
        O1[会话记录]
        O2[评估报告]
    end

    I1 & I2 --> U
    R --> O1 --> O2
```

## 二、User Agent内部

```mermaid
flowchart LR
    subgraph GEN["生成"]
        G1[选择问题]
        G2[Persona包装]
    end

    subgraph LOOP["循环"]
        L1[调用Bot]
        L2[接收回答]
        L3[检测终止]
    end

    subgraph END["结束"]
        E1[保存数据]
    end

    G1 --> G2 --> L1 --> L2 --> L3
    L3 -->|继续| G1
    L3 -->|结束| E1
```

## 三、终止条件检测

```mermaid
flowchart TB
    T{终止?} -->|是| R1{原因?}
    T -->|否| C[继续对话]

    R1 -->|轮数≥20| E1[max_turns]
    R1 -->|转人工| E2[escalation]
    R1 -->|3次无效| E3[invalid]
    R1 -->|满意| E4[satisfied]
```

## 四、提问生成策略

```mermaid
flowchart LR
    A[输入] --> B{策略}
    B -->|模板| C[占位符填充]
    B -->|动态| D[Meta-Prompting]
    B -->|演化| E[Evol-Instruct]
    C & D & E --> F[质量控制]
    F --> G[输出生成]
```

## 五、Referee评估维度

```mermaid
flowchart TB
    subgraph IN2["输入"]
        Q[问题]
        A[回答]
    end

    subgraph EVAL["评分"]
        direction LR
        E1[相关性]
        E2[有用性]
        E3[共情性]
        E4[安全性]
    end

    subgraph OUT2["输出"]
        S[综合得分]
        D[终止决策]
    end

    Q & A --> E1 & E2 & E3 & E4 --> S --> D
```

## 六、数据流转

```mermaid
flowchart LR
    D1[(CSV)] --> D2[(问题池)]
    D2 --> P[仿真引擎]
    P --> D3[(会话记录)]
    D3 --> D4[(分析报告)]
```

## 七、API交互

```mermaid
sequenceDiagram
    participant C as Client
    participant U as UserAgent
    participant T as TargetBot
    participant R as Referee

    C->>U: POST /start
    U->>T: q1
    T-->>U: a1
    U->>R: 评估
    R-->>U: 继续
    U->>T: q2
    T-->>U: a2
    U->>R: 评估
    R-->>U: 结束
    U-->>C: 返回结果
```

## 八、部署架构

```mermaid
flowchart TB
    subgraph CLIENT["客户端"]
        C[API调用]
    end

    subgraph SERVER["服务端"]
        direction LR
        R[Router]
        S[Service]
        A[Agent]
    end

    subgraph DATA["数据"]
        D[(存储)]
    end

    C --> R --> S --> A --> D
```

---

## 设计原则

1. **正方形布局**: 每个流程图控制在3-4层深度
2. **无长链**: 最大节点数8个，避免纵向长链条
3. **模块化**: 使用subgraph分组，内部紧凑
4. **并行展示**: 同级节点横向排列
