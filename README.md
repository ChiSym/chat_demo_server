# chat_demo

This [repo](https://github.com/probcomp/chat_demo/) is forked off the English-to-IQL and GenFact demos. 

It provides a common ChatGPT-style demo interface with two areas at the bottom for input and a chat-style UI above of ever-growing rows.

### Installation

1. Install [poetry](https://python-poetry.org/docs/#installation)
2. `poetry install`
3. `poetry shell`
4. `npm install`

### Development

1. To start the web server, run `uvicorn chat_demo.main:app --reload`
2. To work on the Tailwind CSS, run `npx tailwindcss -i ./src/input.css -o ./dist/output.css --watch`

By default, Tailwind only adds necessary CSS classes, so you can't add unused classes in the browser for experimenting. (There's a commented-out line in the template that loads all Tailwind styles, so you can do this, but it messes with the "Loading..." spinner when used.)

(This was built with [Jujutsu](https://martinvonz.github.io/jj/latest/), a Git-compatible VCS. For the most part, you can ignore this fact and the repo will look like plain Git, unless you really want to see the history or diffs in my personal repo.)

### Production

To start the web server for production, run:
1. `poetry shell`
2. `uvicorn chat_demo.main:app --host 0.0.0.0 --port 60001 --workers 2 > uvicorn.log 2>&1 &`
3. `disown`

`--host 0.0.0.0` tells it to listen from all IP addresses. By default, it only listens to localhost (which is fine for development using SSH tunneling).

`--workers 2` - not sure if 2 is good/bad, but it's what I've been using.

`> uvicorn.log 2>&1 &` - this redirects stdout to uvicorn.log, and redirects stderr to stderr to stdout

`&` - runs it in the background. 

`disown` is used to detach the process from the terminal so it doesn't die when you log out.

