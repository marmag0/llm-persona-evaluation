import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage ,HumanMessage, AIMessage


def init_model(conversation_type: str = "human_in_the_loop", input_prompts: str = None):
    """
    Function used for selecting the mode of conversation with LLM provided via API.
    conversation_type:
        - human_in_the_loop: classic conversation with LLM in chat interface
        - automated_test: batch processing of many input prompts one after another
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
    
    # model's persona
    SYSTEM_PROMPT = "You are a pirate, all yout answaers should be structured like an old pirate with 'Arrr', 'Grrrr' and other pirate-like additives."   

    # conversation history
    messages = [
        SystemMessage(content="SYSTEM_PROMPT"),
    ]

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
        try:
            with open(input_prompts, 'r') as file:
                for prompt in file:

                    messages.append(HumanMessage(prompt))
                    print(f"User: {prompt}", end="")
                    
                    response = chat.invoke(messages)
                    messages.append(AIMessage(response.content))
                    print(f"AI: {response.content}")
                    print("------------------------------")
        except:
            print("Error while loading prompts! Exiting...")


if __name__ == "__main__":
    init_model(conversation_type="human_in_the_loop")
    #init_model(conversation_type="automated_test", input_prompts="prompts.txt")
