# AGENTIC CHATBOT
developer - BHAVISHYA SHARMA

## Overview
This is a simple chatbot which has two tools : 1) web_search() and 2) query_ui():<br>
- web_search : searches web and gets the results in structured string format<br>
- query_ui : searches cached ui elements from vector_db

and rest is upto the llm and prompt

## Specs
LLM API : groq (very generous people)<br>
Summarizing and Embedding : Locally via Ollama<br>
Summarizing Model : ibm/granite4.1:3b |  Embedding Model : all-minilm:l6-v2<br>
Chat API : OpenAI chat completions<br>
Main LLM Model used : GPT-OSS-20B<br>
Web Search API : ddgs-python (again, very generous)<br>
VectorDB : Chromadb

## Setup
1. Download Ollama
- 1. Download the models (embedding and summarizing) listed in `specs` 
- 2. check your port number for ollama (im using it like this : ```client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="",
)``` )
2. Make your python virtual environment using `environment.yml` file
3. Get your API key from groq

## Usage
To use the project, you'll have to do some preprocessing (if you want to use the query_ui feature otherwise skip these Phase1 and Phase2) : <br>
## 1.
### <p align="center">  Phase 1</p>
1. Find **scraper.py** in root dir, find this line `if __name__ == "__main__":`, just under it see `target_url = "something"`
2. In place of "something", give the url of your website
3. Run the Script as `python scraper.py`
4. It would make data/website_snapshots/your_webpage.json

### <p align="center">  Phase 2</p>
1. Find **flattenNindex.py**
2. Run it like :  `flattenNindex.py [-h] [--page PAGE] [--desc DESC] [--db DB] [--query QUERY] snapshot_file`<br>
  --page is the string html pagename that is shown to user <br>
  --db is string db name (optional)<br>
  --query is the string for a particular feature (optional)<br>
  snapshot_file is the path to the json file we just created<br>
  - **you provide --query only when you want to test what the database retrieves otherwise leave**<br>
  - **Remember that you can provide collection name in this file by line `COLLECTION_NAME = "ui_elements"`** 
-  **If you provide collection name (default ui_elements), then change this line: `                        "enum": ["ui_elements"]` in ai_backend.py**<br>

   
## 2.
1. Now just go localhost/index.html and start the thing
2. **remember** : this chatbot doesn't have chat history context(i wanted to keep it simple), you can just add it using summarizer and some extra logic of sql and vector database and some userid.
   <br> <br>
## Adding Tools
### Phase 1 - Make The Function Implementation
1. Go to tools.py
2. Make your function which logs to the variable `logger` currently it logs to `logs/ai_backend.log` but you can change it by searching `logger.config` 

### Phase 2 - Add The Tool to the Agent
1. Search `Tool Registry`, youll see `TOOLS` variable, add your tool definition in Json format following that given structure strictly. **remember:** it is mandatory to give required = [_all parameters_] otherwise it raises error
2. Now Find `Tool Executor` and in it find the variable `AVAILABLE_TOOLS`, just import the tool and put it there.
  
## Logs
All the logging is done in `logs`<br>
For python related it is `ai_backend.log`<br>
and for php related it is `php_logs.log`<br>
`test.log` is only for testing purposes<br>
`tools.log` is where i used to log tool calls

Currently I log (int the following order) : <br>
- Current Chat Context as `Context 1` where 1 is Round which specifies how many rounds it is taking to answer<br>
- Tool Call <br>
- Tool Result <br>
- And some more logs by ollama and groq




