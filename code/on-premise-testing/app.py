import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage ,HumanMessage, AIMessage


def init_model(conversation_type: str = "human_in_the_loop") -> tuple[ChatOpenAI, list]:
    """
    Function used for selecting the mode of conversation with LLM provided via API.
    conversation_type:
        - human_in_the_loop: classic conversation with LLM in chat interface
        - automated_test: used only for model init to allow performing automated tests on it
    """
    api_key = os.getenv("API_KEY")
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
    
    # defining the type of used conversation
    if conversation_type == "human_in_the_loop":
        SYSTEM_PROMPT = """
        Jesteś piratem, odpowiadaj na pytania utrzymując styl wypowedzi piratów i co jakiś czas dorzuć 'Arrrr' lub inne pirackie akcenty.
        """

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
    
    elif conversation_type == "automated_test":
        pass


if __name__ == "__main__":
    chat, messages = init_model(conversation_type = "human_in_the_loop")