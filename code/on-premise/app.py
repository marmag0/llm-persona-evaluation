import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage ,HumanMessage, AIMessage


def init_model(conversation_type: str = "human_in_the_loop", system_prompt: str = "", test_file: str = None):
    """
    Function used for launching the LLM in specified interaction modes:
    - human_in_the_loop - standard chat mode
    - automated_test - scenario with sequence of prompts pulled form file
    """

    api_key = os.getenv("API_KEY")
    # fallback if env not loaded
    if not api_key:
        load_dotenv()
        api_key = os.getenv("API_KEY")

    # OpenAI API model selection
    chat = ChatOpenAI(
        model="gpt-5-nano-2025-08-07",
        api_key=api_key,
        temperature=0.3
    )
    
    # model's persona
    path = Path(system_prompt)
    if path.exists():
        SYSTEM_PROMPT = path.read_text(encoding="utf-8")
    else:
        SYSTEM_PROMPT = """
    """

    # defining the type of used conversation
    print("\n")
    if conversation_type == "human_in_the_loop":
        
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
    
    elif conversation_type == "automated_test":
        pass

if __name__ == "__main__":
    init_model(conversation_type="human_in_the_loop", system_prompt="./system.xml")
