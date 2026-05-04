import os
import re
import json
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

#from vfs_prod import VirtualFileSystem

# ------------------------------------------------------------------
