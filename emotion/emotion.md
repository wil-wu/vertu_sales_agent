# LoveActually.AI 系统架构图

## 一、整体系统架构

```mermaid
flowchart TB
    subgraph USER["用户层"]
        U[用户]
    end

    subgraph CORE["核心Agent系统"]
        direction TB

        subgraph INTENT["意图识别"]
            I{Intent Engine}
        end

        subgraph AGENTS["专业Agent集群"]
            direction LR
            A1[Astute<br/>AI Matchmaker]
            A2[Profile Analyst<br/>9维标签]
            A3[Behavioral Analyst<br/>心理画像]
            A4[Loving Kitty<br/>聊天伴侣]
            A5[Love Recorder<br/>报告生成]
            A6[Data Analyst<br/>记忆更新]
        end
    end

    subgraph MEMORY["记忆系统"]
        M[(用户画像库)]
    end

    subgraph OUTPUT["输出层"]
        O1[自然语言回复]
        O2[JSON结构化数据]
        O3[AI Report]
    end

    U --> I
    I -->|dating_coach| A1
    I -->|ai_matchmaker| A1
    I -->|general_chat| A4

    A1 <--> A2
    A1 <--> A3
    A4 --> A6
    A2 --> A5
    A3 --> A5

    A6 --> M
    M --> A4

    A1 --> O1
    A2 --> O2
    A3 --> O2
    A4 --> O1
    A5 --> O3
```

## 二、Agent交互流程

```mermaid
sequenceDiagram
    participant U as 用户
    participant I as Intent Engine
    participant A as Astute
    participant P as Profile Analyst
    participant B as Behavioral Analyst
    participant L as Loving Kitty
    participant D as Data Analyst
    participant M as 记忆库

    Note over U,M: 场景1: 新用户注册
    U->>A: 语音对话(人格收集)
    A->>P: 抽取9维标签
    A->>B: 构建心理画像
    P-->>M: 保存标签
    B-->>M: 保存画像

    Note over U,M: 场景2: 日常聊天
    U->>I: 发送消息
    I->>I: 识别意图
    I->>L: 路由到聊天Agent
    L->>M: 读取用户画像
    M-->>L: 返回长期记忆
    L->>D: 每5轮更新记忆
    D->>M: 增量更新画像
    L-->>U: 自然语言回复

    Note over U,M: 场景3: 查看匹配对象
    U->>A5: 请求AI Report
    A5->>M: 读取双方画像
    A5->>A5: 生成兼容性分析
    A5-->>U: AI Report + 破冰建议
```

## 三、Astute Agent详解

```mermaid
flowchart TB
    subgraph INPUT["输入"]
        U[用户语音/文字]
    end

    subgraph PROCESS["处理流程"]
        direction TB
        I[身份锚定<br/>I'm Astute, your Dating Coach]
        T[语调控制<br/>尖刻精准+数据洞察]
        C[反AI格式化<br/>无Markdown/无列表]
        S[口语化风格<br/>短句+碎片化]
    end

    subgraph OUTPUT["输出"]
        O[自然对话<br/>无AI痕迹]
    end

    U --> I --> T --> C --> S --> O
```

## 四、意图分类决策树

```mermaid
flowchart TB
    START([用户消息]) --> CHECK{关键词匹配}

    CHECK -->|如何回复/分析聊天| A[dating_coach<br/>约会教练]
    CHECK -->|评判资料/没匹配| B[ai_matchmaker<br/>AI媒人]
    CHECK -->|其他| C[general_chat<br/>闲聊]

    A --> A1[战术建议]
    A --> A2[回复脚本]
    A --> A3[资料优化]

    B --> B1[兼容性分析]
    B --> B2[资料评判]

    C --> C1[问候]
    C --> C2[情绪宣泄]
    C --> C3[随意聊天]

    A1 & A2 & A3 --> END1([Astute处理])
    B1 & B2 --> END2([Astute处理])
    C1 & C2 & C3 --> END3([Loving Kitty处理])
```

## 五、用户画像构建流程

```mermaid
flowchart LR
    subgraph INPUT["输入数据"]
        V[语音访谈]
        T[文字描述]
        S[已有标签]
    end

    subgraph PROCESS["处理层"]
        direction TB
        P1[Astute收集]
        P2[Profile Analyst<br/>抽取标签]
        P3[Behavioral Analyst<br/>构建画像]
    end

    subgraph STORAGE["存储层"]
        M1[9维标签]
        M2[心理画像JSON]
        M3[风险标记]
    end

    V --> P1
    T --> P2
    S --> P2
    P1 --> P3
    P2 --> M1
    P3 --> M2
    P3 --> M3
```

## 六、长期记忆更新机制

```mermaid
flowchart TB
    subgraph TRIGGER["触发条件"]
        T[每5轮对话]
    end

    subgraph INPUT["输入"]
        E[已有画像]
        R[最近对话]
    end

    subgraph RULES["更新规则"]
        direction LR
        R1[增量<br/>添加新信息]
        R2[覆盖<br/>解决冲突]
        R3[推理<br/>隐式信息]
    end

    subgraph OUTPUT["输出"]
        U[更新后画像]
    end

    T --> R
    E --> R
    R --> R1 & R2 & R3 --> U
```

## 七、反AI设计原则

```mermaid
flowchart TB
    subgraph NORMAL["典型AI回复"]
        A1["感谢您的咨询，<br/>我认为您的问题很有趣..."]
        A2["1. 首先...<br/>2. 其次...<br/>3. 最后..."]
        A3["😊😊 很高兴为您服务 😊😊"]
    end

    subgraph TRANSFORM["反AI转换"]
        T[转换规则]
    end

    subgraph RESULT["LoveActually风格"]
        B1["真的假的？<br/>先说完你的情况"]
        B2["首先...还有...<br/>最后..."]
        B3["~ 行吧"]
    end

    A1 --> T
    A2 --> T
    A3 --> T
    T --> B1
    T --> B2
    T --> B3
```

## 八、数据流全景图

```mermaid
flowchart TB
    subgraph LAYER1["Layer 1: 输入层"]
        I1[语音]
        I2[文字]
        I3[历史记录]
    end

    subgraph LAYER2["Layer 2: 意图层"]
        INT{Intent Classification}
    end

    subgraph LAYER3["Layer 3: Agent层"]
        direction LR
        A1[Astute]
        A4[Loving Kitty]
    end

    subgraph LAYER4["Layer 4: 分析层"]
        direction LR
        AN1[Profile Analyst]
        AN2[Behavioral Analyst]
        AN3[Data Analyst]
    end

    subgraph LAYER5["Layer 5: 记忆层"]
        M[(User Profile DB)]
    end

    subgraph LAYER6["Layer 6: 输出层"]
        O1[聊天回复]
        O2[结构化数据]
        O3[AI Report]
    end

    I1 & I2 --> INT
    I3 --> LAYER3
    I3 --> LAYER5

    INT --> A1 & A4

    A1 --> AN1 & AN2
    A4 --> AN3

    AN1 & AN2 & AN3 --> M
    M --> A4

    A1 --> O1
    AN1 & AN2 --> O2
    AN1 --> O3
    A4 --> O1
```

## 九、关键设计模式

```mermaid
flowchart LR
    subgraph PATTERNS["核心设计模式"]
        direction TB
        P1["🎭 Role Anchoring<br/>角色锚定"]
        P2["🚫 Anti-AI Training<br/>反AI训练"]
        P3["📝 Strict JSON<br/>严格JSON输出"]
        P4["🧠 Incremental Memory<br/>增量记忆"]
        P5["🌐 Language Consistency<br/>语言一致性"]
        P6["🎯 Intent Routing<br/>意图路由"]
    end

    subgraph BENEFITS["收益"]
        direction TB
        B1[真实对话体验]
        B2[结构化数据]
        B3[长期记忆]
        B4[多语言支持]
    end

    P1 --> B1
    P2 --> B1
    P3 --> B2
    P4 --> B3
    P5 --> B4
    P6 --> B1
```

## 十、系统状态流转

```mermaid
stateDiagram-v2
    [*] --> Onboarding: 新用户

    Onboarding --> AstuteChat: 语音收集
    AstuteChat --> ProfileBuilding: 数据分析
    ProfileBuilding --> Matching: 画像完成

    Matching --> LovingChat: 找到匹配
    Matching --> AstuteChat: 寻求建议

    LovingChat --> MemoryUpdate: 每5轮
    MemoryUpdate --> LovingChat: 记忆刷新

    AstuteChat --> ProfileBuilding: 补充信息

    LovingChat --> ReportGeneration: 查看资料
    ReportGeneration --> LovingChat: 获得建议

    MemoryUpdate --> [*]: 会话结束
    ReportGeneration --> [*]: 退出
```

---

## 图例说明

| 符号 | 含义 |
|-----|------|
| ⭕ 圆形 | 开始/结束节点 |
| 🔷 菱形 | 决策/判断节点 |
| 🟦 矩形 | 处理/Agent节点 |
| 🗄️ 圆柱 | 数据存储 |
| ➡️ 箭头 | 数据流向 |
| --- 虚线 | 异步/后台流程 |
