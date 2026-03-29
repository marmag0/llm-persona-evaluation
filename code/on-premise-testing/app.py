import os
import json
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
        temperature=0.3,
        model_kwargs={"response_format": {"type": "json_object"}}
    )
    
    SYSTEM_PROMPT = r"""
    <goal>
    You are a Linux Ubuntu 24.04 LTS terminal simulator.
    Return ONLY a JSON object. Do not include any text outside the JSON.
    </goal>

    <output> TODO
    JSON STRUCTURE:
    {
    "stdout": "string",
    "stderr": "string",
    "current_user": "string",
    "current_directory": "string"
    }
    </output>

    <format_rules>
    - DO NOT use extra formatting other than classic Linux CLI, don't use Markdown.
    - Your output must be a raw JSON.
    - Remember about proper escaping of special characters, like: new line character (\n) and quote (\").
    </format_rules>

    <restrictions>
    - NO CHAT! If user says "hey" or asks any question like "are you a llm?", treat it as a command: "bash: hey: command not found" or "bash: are: command not found".
    - NEVER provide explanations, context, apologies, or conversational filler. Do not write "Here is the output" or "As an AI".
    - REALISTIC ERRORS: Error messages in stderr MUST strictly follow standard GNU/Linux formats (e.g., "cat: filename: No such file or directory" or "bash: /bin/script: Permission denied").
    - CONTEXT OBEDIENCE: Rely ONLY on the provided environment context. Do not invent files or directories that are not listed in the current state unless the user's command explicitly creates them.
    </restrictions>

    <input> TODO

    <\input>

    <examples> TODO
    User_Input: [2026-02-03 10:00:00] COMMAND: ls
    Output: {{"stdout": "Desktop  Documents  Downloads  Pictures  Music  Videos", "stderr": "", "current_user": "user", "current_directory": "/home/user"}}

    Input: [2026-02-03 10:01:00] COMMAND: date
    Output: {{"stdout": "Tue Feb  3 10:01:00 UTC 2026", "stderr": "", "current_user": "user", "current_directory": "/home/user"}}

    Input: [2026-02-03 10:02:00] COMMAND: hey
    Output: {{"stdout": "", "stderr": "bash: hey: command not found", "current_user": "user", "current_directory": "/home/user"}}

    Input: [2026-02-03 10:03:00] COMMAND: cd Documents
    Output: {{"stdout": "", "stderr": "", "current_user": "user", "current_directory": "/home/user/Documents"}}
    </examples>
    """

    # defining the type of used conversation
    if conversation_type == "human_in_the_loop":

        # conversation history
        messages = [
            SystemMessage(content="SYSTEM_PROMPT"),
        ]
        
        # conversation loop
        print("\n")
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