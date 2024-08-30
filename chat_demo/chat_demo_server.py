from fastapi import FastAPI, Request, Form
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2_fragments.fastapi import Jinja2Blocks
from typing import Annotated, Callable
from itertools import count
from pathlib import Path


import ipdb
import jinja2
import logging as log
import http.client as http_client


def log_http_output():
    '''Log HTTP input/output to the console'''
    http_client.HTTPConnection.debuglevel = 1

    log.basicConfig()
    log.getLogger().setLevel(log.DEBUG)
    requests_log = log.getLogger("requests.packages.urllib3")
    requests_log.setLevel(log.DEBUG)
    requests_log.propagate = True

log_http_output()


class ChatDemoServer:
    def __init__(self, *, root_template: str = "index.html.jinja", templates: Jinja2Blocks, default_context: dict, query1_callback: Callable, query2_callback: Callable):
        self.app = FastAPI()
        self.app.mount("/static", StaticFiles(directory="dist"), name="static")
        self.query_counter = count(1)

        self.root_template = root_template
        self.templates = templates
        self.default_context = default_context
        self.query1_callback = query1_callback
        self.query2_callback = query2_callback

    @staticmethod
    def get_templates(templates_path: str):
        """
        Create and return a Jinja2Blocks instance for the given templates path, 
        including the chat-demo's templates. 
        
        :param templates_path: A string or path to the templates directory
        :return: Jinja2Blocks instance
        """
        current_dir = Path(__file__).resolve().parent
        module_src_dir = current_dir.parent / "src"
       
        loader = jinja2.ChoiceLoader([
            jinja2.FileSystemLoader(templates_path),
            jinja2.FileSystemLoader(module_src_dir)
        ])
        return Jinja2Blocks(directory="IGNORE THIS", loader=loader)


    def setup_routes(self):
        @self.app.exception_handler(Exception)
        async def debug_exception_handler(request: Request, exc: Exception):
            ipdb.set_trace()
            return JSONResponse(
                status_code=500,
                content={"message": "Internal Server Error"}
            )
        
        @self.app.get("/")
        async def root(request: Request):
            return self.templates.TemplateResponse(
                self.root_template,
                self.default_context | 
                {"request": request, 
                 "idnum": next(self.query_counter),
                 "root": True},
            )

        @self.app.post("/query1")
        async def query1(request: Request, english_query: Annotated[str, Form()]):
            return await self.query1_callback(request, english_query, self.query_counter)

        @self.app.post("/query2")
        async def query2(request: Request):
            form_data = dict(await request.form())
            log.debug(f"Request form data: {form_data}")

            return await self.query2_callback(request, self.query_counter, **form_data)

    def get_app(self):
        return self.app
    
