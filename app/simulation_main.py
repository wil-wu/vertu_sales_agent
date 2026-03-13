"""仿真模拟测试主流程
- 检索管道:
    - FAQ
    - 价格API
    - Graph
1, 读取输入参数
    - 输入参数包括：
        - 渠道[国内/海外]
        - 待仿真维度(总计32个维度)
    - 检索管道知识 检索结果形成知识子集
2, 获取单个session知识
    - 从知识子集随机组合20份知识 -> 单个session知识池
3, 单个session仿真
    - 用户维度画像(1/7维)
    - 用户意图画像(1/5维)
    - 组合知识池
    - 增量上下文
    *-> 生产用户问题 + 预期答案
    -> 调用AI sales Agent
    -> 保持后续流程一致 
"""


import random


class SimulationMain:
    def __init__(self, config: dict, excute_config: dict):
        self.config = config
        self.excute_config = excute_config

    def run(self):
        # 根据输入参数 执行检索管道知识检索 检索结果形成知识子集
        knowledge_subset = self.search_knowledge()
        
        # 根据知识子集 随机组合20份知识 形成知识池
        knowledge_pool = self.generate_session_knowledge_pool(knowledge_subset)

        # 根据知识池 用户维度画像(1/7维) 用户意图画像(1/5维) 组合知识池 增量上下文 生产用户问题 + 预期答案 调用AI sales Agent 保持后续流程一致
        session_simulation = self.generate_session_simulation(knowledge_pool)

        pass

    def search_knowledge(self):
        faq_results = self.search_faq()
        price_results = self.search_price()
        graph_results = self.search_graph()
        return {"faq": faq_results, "price": price_results, "graph": graph_results}

    def generate_session_knowledge_pool(self, knowledge_subset):
        """
        根据知识子集 随机组合20份知识 形成知识池, 数据结构与父集一致, 即:
        [{"faq": faq_results', "price": price_results', "graph": graph_results'}, ...]
        - 子集总量<20份知识 即返回的每个元素中对应的key 取到的值长度不超过20 
        - session_count 为知识池中元素的总数, 即返回的列表长度
        todo:
            随机取值优先保障单子集管道取到的值不重复
        """
        knowledge_pool = []
        for _ in range(self.excute_config["session_count"]):
            knowledge_pool.append({
                "faq": random.sample(knowledge_subset["faq"], min(20, len(knowledge_subset["faq"]))),
                "price": random.sample(knowledge_subset["price"], min(20, len(knowledge_subset["price"]))),
                "graph": random.sample(knowledge_subset["graph"], min(20, len(knowledge_subset["graph"]))),
            })
        return knowledge_pool

    def generate_session_simulation(self, session_knowledge_pool):
        pass

if __name__ == "__main__":
    config = {
        "channel": "国内",
        "dimensions": ["维度1", "维度2", "维度3"],
        "session_count": 800, # 3/32 ~= 10% then *8000  + 2000 = 10000 == 8000 单维度  + 2000 交叉维度
    }
    excute_config = {
        "max-turns": 10, # 每轮对话最大轮数
        "output-dir": "output", # 输出文件夹路径
        "parallel": 10, # 并行执行的对话数
    }
    simulation_main = SimulationMain(config, excute_config)
    simulation_main.run()