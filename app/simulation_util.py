"""
提供仿真过程补充检索管道
"""

import json
import os
from pandas._config.config import F
import requests

REACT_AGENT_FAQ_URL = os.environ.get("REACT_AGENT_FAQ_URL")
REACT_AGENT_PRICE_URL = os.environ.get("QUESTION_POOL_PRICE_URL")
REACT_AGENT_GRAPH_URL = os.environ.get("REACT_AGENT_GRAPH_URL")

class SearchUtil:
    def __init__(self, config: dict):
        self.config = config
    #     config = {
    #     "channel": "国内",
    #     "dimensions": ["维度1", "维度2", "维度3"],
    #     "session_count": 800, # 3/32 ~= 10% then *8000  + 2000 = 10000 == 8000 单维度  + 2000 交叉维度
    # }

    def search_faq(self):
        url = REACT_AGENT_FAQ_URL
        results = []
        for query in self.config["query_list"]:
            for collection_name in self.config["collection_names"]:
                body = {
                    "query": query,
                    "top_k": 10,
                    "collection_names": [
                        collection_name
                    ]
                }
                response = requests.post(url, json=body)
                results.append(response.json())
        return results

    def search_price(self):
        url = REACT_AGENT_PRICE_URL
        mock = {
        "hits": [
            {
            "additionalProp1": {}
            }
        ],
        "page": 0,
        "hits_per_page": 0,
        "total_pages": 0,
        "total_hits": 0
        }
        return mock

    def search_graph(self):
        url = REACT_AGENT_GRAPH_URL.replace("nl2graph_qa", "direct_cypher_query")
        results = []
        for product_name in self.config["product_names"]:
            # for is_oversea in [True, False]:
            for is_oversea in [False]:
                for path_len in range(0, self.config["max_path_len"] + 1):
                    body = {
                        "product_name": product_name,
                        "path_len": path_len,
                        "is_oversea": is_oversea
                        }
                    response = requests.post(url, json=body)
                    results.append(response.json())
        return results

def middle_gen():
    config = {
        "collection_names": ["domestic_e_commerce","domestic_general","oversea_private","preceding_questions"],
        "query_list": ["屏幕分辨率", "屏幕尺寸", "屏幕类型"],
        "product_names": ["VERTU AGENT Q"],
        "max_path_len": 2,
        "session_count": 800, # 3/32 ~= 10% then *8000  + 2000 = 10000 == 8000 单维度  + 2000 交叉维度
    }
    search_util = SearchUtil(config)
    faq = search_util.search_faq()
    graph = search_util.search_graph()
    price = search_util.search_price()
    with open("middle_gen.json", "w", encoding="utf-8") as f:
        f.write(json.dumps({"faq": faq, "graph": graph, "price": price}, ensure_ascii=False, indent=4))

if __name__ == "__main__":
    middle_gen()