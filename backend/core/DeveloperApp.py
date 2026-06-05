
############################################################################################################
# Following code must be used at the start of the application. It may raise exception in case it is not used 
# at the start of the application.
# Important to note: 
# 1) InitAOI() will setup llm and embeddings. Developer is not allowed to use it explicitly 
# and update Settings. Please en
# 2) Please ensure you copy madatory lib folder as part of this applicaiton. and use CustomAOI_helper.py to 
#   start building your application.
############################################################################################################

from CustomAOI_helper import InitAOI


deploymentName = "iotdepoc-gpt-35-turbo"
embDeploymentName="iotdepoc-text-embedding-ada-002"
llmModel="gpt-35-turbo"
embModel="text-embedding-ada-002"

secure_models=InitAOI(__name__, '<USER NAME>', '<PASSWORD>', llmModel, deploymentName, embModel, embDeploymentName)

####################### Developer Code Start from here ###############################
# Here is the Sample application
######################################################################################
from llama_index.core.tools import FunctionTool
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.agent import ReActAgent
#from llama_index.core import Settings


# define sample Tool
def multiply(a: int, b: int) -> int:
    """Multiple two integers and returns the result integer"""
    return a * b


multiply_tool = FunctionTool.from_defaults(fn=multiply)

def add(a: float, b: float) -> float:
    """Add two numbers and returns the sum"""
    return a + b


add_tool = FunctionTool.from_defaults(fn=add)

def subtract(a: float, b: float) -> float:
    """Subtract two numbers and returns the subtraction"""
    return a - b


subtract_tool = FunctionTool.from_defaults(fn=subtract)


agent = ReActAgent.from_tools([multiply_tool, add_tool, subtract_tool], verbose=True)


agent.chat("What is 10 + 30 * (100+20) - 1000")


documents = SimpleDirectoryReader("./data").load_data()
index = VectorStoreIndex.from_documents(documents)
query_engine = index.as_query_engine()

response = query_engine.query(
    "Please summarize this document."
)
print(response)

#########################LLM CALLING EXAMPLE ######################################
chat_messages = [
    ChatMessage(role=MessageRole.SYSTEM, content="You are a helpful AI assistant."),
    ChatMessage(role=MessageRole.USER, content="Write a short poem about technology.")
]
response = secure_models.chat(chat_messages)
# print("Chat completion response:")
print(response.message.content)
print("\n" + "-"*50 + "\n")


 
response = secure_models.chat([
    ChatMessage(role=MessageRole.USER, content="Write a report on AI trends")
])
print(response.message.content)
print("\n" + "-"*50 + "\n") 
# And generate embeddings as needed
embeddings = secure_models.embedder.get_text_embedding_batch(["Text to embed"])
print("Embeddings for the text:")
print(embeddings[0])

# # Example 2: Generate text completion
prompt = "Complete this sentence: The future of artificial intelligence is"
completion = secure_models.complete(prompt)
print("Text completion response:")
print(f"{prompt} {completion.text}")
print("\n" + "-"*50 + "\n")
 
# Example 3: Generate embeddings for a list of texts
texts = [
    "Artificial intelligence is transforming industries",
    "Machine learning models require large amounts of data",
    "Neural networks are inspired by the human brain"
]
embeddings = secure_models.embedder.get_text_embedding_batch(texts)
print("Embeddings for multiple texts:")
print(f"Generated {len(embeddings)} embeddings")
print(f"Dimension of each embedding: {len(embeddings[0])}")
print("\n" + "-"*50 + "\n")


 
