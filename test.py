import chainlit as cl
import boto3
from langchain_aws import ChatBedrockConverse
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory

# --- Configuration ---

# 1. Set up the AWS Bedrock client
# (Pulls credentials from your 'aws configure' setup or env variables)
bedrock_client = boto3.client(
    service_name="bedrock-runtime",
    region_name="us-east-1"  # IMPORTANT: Change this to your Bedrock region
)

# 2. Define the Llama 3 model ID
# You can find other model IDs in your AWS Bedrock console
LLAMA_3_MODEL_ID = "meta.llama3-8b-instruct-v1:0"

# -----------------------


@cl.on_chat_start
async def on_chat_start():
    """
    This function runs when a new chat session starts.
    It initializes the LangChain components for that session.
    """
    
    llm = ChatBedrockConverse(
        model="openai.gpt-oss-120b-1:0",
        region_name="us-east-1",
        temperature=0.3,
        max_tokens=4096
    )

    # Initialize the LangChain ConversationChain
    # This chain automatically uses a ConversationBufferMemory
    # This is the "In-Session Memory"
    conversation_chain = ConversationChain(
        llm=llm,
        verbose=True,  # Good for debugging
        memory=ConversationBufferMemory()
    )

    # *** THIS IS THE KEY TO PERSISTENCE ***
    # Store the initialized chain in the Chainlit user session
    # Chainlit automatically handles saving/loading this session
    cl.user_session.set("chain", conversation_chain)

    await cl.Message(content="Hello! How can I assist you today?").send()


@cl.on_message
async def on_message(message: cl.Message):
    """
    This function runs every time the user sends a message.
    """
    
    # Retrieve the specific ConversationChain for this user's session
    chain = cl.user_session.get("chain")

    # This callback streams the LLM's response to the UI
    cb = cl.AsyncLangchainCallbackHandler()

    # Run the chain asynchronously
    # The 'ainvoke' method will automatically:
    # 1. Load the history from the 'memory' object
    # 2. Append the new 'message.content'
    # 3. Send it all to Llama 3
    # 4. Get the response
    # 5. Save the new input and response to the 'memory' object
    response = await chain.ainvoke(message.content, callbacks=[cb])

    # Send the final response from the chain
    # The actual text is in the "response" key
    await cl.Message(content=response["response"]).send()