import os
from typing import Literal
from langchain_openai import ChatOpenAI
from tavily import TavilyClient
from deepagents import create_deep_agent
from dotenv import load_dotenv

load_dotenv()

rewrite_llm = ChatOpenAI(
    # model="XiaomiMiMo/MiMo-V2-Flash",
    model="deepseek-ai/DeepSeek-R1",
    temperature=0.0,
    max_tokens=128 * 1024,  # type: ignore
    api_key=os.getenv("LLM_API_KEY"),
    # base_url="https://api-inference.modelscope.cn/v1",
    base_url="https://api.siliconflow.cn/v1",
)

tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
):
    """Run a web search"""
    return tavily_client.search(
        query,
        max_results=max_results,
        include_raw_content=include_raw_content,
        topic=topic,
    )

# System prompt to steer the agent to be an expert researcher
research_instructions = """
你是一名专家研究员。你的工作是进行全面的研究，然后写出一份精美的报告。 你可以使用互联网搜索工具作为收集信息的主要手段。 
## `internet_search` 使用该工具对给定的查询进行互联网搜索。你可以指定返回结果的最大数量、主题以及是否包含原始内容。
"""

agent = create_deep_agent(
    model=rewrite_llm,
    tools=[internet_search],
    system_prompt=research_instructions
)

result = agent.invoke({"messages": [{"role": "user", "content": ""}]})

# Print the agent's response
print(result)