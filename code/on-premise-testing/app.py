import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage ,HumanMessage, AIMessage

api_key = os.getenv("API_KEY")
SYSTEM_PROMPT = """
Jesteś piratem, odpowiadaj na pytania utrzymując styl wypowedzi piratów i co jakiś czas dorzuć 'Arrrr' lub inne pirackie akcenty.
"""

# fallback if not contenerized
if not api_key:
    load_dotenv()
    api_key = os.getenv("API_KEY")

# OpenAI API model selection
chat = ChatOpenAI(
    model="gpt-5-nano-2025-08-07",
    api_key=api_key,
    temperature=0.3
)

# conversation history
messages = [
    SystemMessage(content="SYSTEM_PROMPT"),
]

# conversation loop
while True:
    prompt = str(input("User: "))

    if prompt == "/exit":
        break

    messages.append(HumanMessage(prompt))

    response = chat.invoke(messages)
    messages.append(AIMessage(response.content))
    print(f"AI: {response.content}")
    print("------------------------------")