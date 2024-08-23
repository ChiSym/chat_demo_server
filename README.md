# chat-demo

This [repo](https://github.com/probcomp/chat_demo/) is forked off the English-to-IQL and GenFact demos. 

It provides a common ChatGPT-style demo interface with two areas at the bottom for input and a chat-style UI above of ever-growing rows.

## Usage

1. Add as a dependency in your pyproject.toml file: `chat-demo = { git = "https://github.com/probcomp/chat_demo_server.git", rev = "SOME SHA HERE" }
2. Create two Jinja templates, one for the second query area (after the English query), and one for each row's results area.
3. In your main file, add the following code to set it up:

```python
from chat_demo.chat_demo_server import ChatDemoServer

templates = ChatDemoServer.get_templates("your_template_directory")

default_context = {"page_title": "My demo's name",
                   "extra_js_scripts": "<script goes here..."
                   "extra_css": "<style goes here...",
                   "english_query_placeholder": "Ask your question in plain English",
                   "row_result_template": "row_result_my_demo.html.jinja", # the name of your row result template file
                   "query2_template": "query2_my_demo.html.jinja"} # the name of your query2 template file

async def query1_callback(request: Request, english_query: str, query_counter):
    '''This callback will handle the first, plain English query. 
       It must return the "query2" block
    '''
    ...

async def query2_callback(request: Request, query_counter, **kwargs):
    '''This callback will handle the second query, with all form params in kwargs.
       It must return the "plot" block (which will include the row_result template.)
    '''
    ...

# Create and setup the server
server = ChatDemoServer(templates, default_context, query1_callback, query2_callback)
server.setup_routes() # Create the default routes
app = server.get_app() # Expose the app for uvicorn CLI
```

For examples, see the genfact_demo and english_to_iql_demo repos.


### Development

1. Install [poetry](https://python-poetry.org/docs/#installation)
2. `poetry install`
3. `poetry shell`
4. `npm install`

5. To start the web server, run `uvicorn chat_demo.main:app --reload`
6. To work on the Tailwind CSS, run `npx tailwindcss -i ./src/input.css -o ./dist/output.css --watch`

By default, Tailwind only adds necessary CSS classes, so you can't add unused classes in the browser for experimenting. (There's a commented-out line in the template that loads all Tailwind styles, so you can do this, but it messes with the "Loading..." spinner when used.)
