# test_gpt_oss_langchain.py
import os
from langchain_aws import ChatBedrockConverse
from dotenv import load_dotenv

load_dotenv()

print("Testing GPT-OSS with LangChain ChatBedrockConverse...\n")

# Try with GPT-OSS
llm = ChatBedrockConverse(
    model="global.anthropic.claude-haiku-4-5-20251001-v1:0",
    temperature=0.3,
    max_tokens=500
)

# Test query
response = llm.invoke("What's 17 * 13?")

print("Response:")
print(response.content)
print("\n" + "="*50 + "\n")
print(response)
# Check response structure
print("Response type:", type(response))
print("Has usage_metadata:", hasattr(response, 'usage_metadata'))

if hasattr(response, 'usage_metadata') and response.usage_metadata:
    print("Token usage:", response.usage_metadata)
