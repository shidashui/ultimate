import anthropic
from config.configs import MODEL

# 原有同步客户端保持不变，供 Cli 使用
client = anthropic.Anthropic(
    api_key=MODEL["api_key"],
    base_url=MODEL["base_url"]
)

# 新增异步客户端，供 Gateway 使用
async_client = anthropic.AsyncAnthropic(
    api_key=MODEL["api_key"],
    base_url=MODEL["base_url"]
)

def message_client(**kwargs):
    kwargs["model"] = MODEL["name"]
    return client.messages.create(**kwargs)

async def async_message_client(**kwargs):
    kwargs["model"] = MODEL["name"]
    return await async_client.messages.create(**kwargs)

def stream_client(**kwargs):
    kwargs["model"] = MODEL["name"]
    return client.messages.stream(**kwargs)

def message_client_stream(**kwargs):
    kwargs["model"] = MODEL["name"]
    return client.messages.stream(**kwargs)

if __name__ == "__main__":
    print('123')