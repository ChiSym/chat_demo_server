import shutil
from pathlib import Path
from importlib import resources

def main():
    # with resources.as_file(resources.files('chat_demo').joinpath('dist/output.css')) as source:
    with resources.as_file(resources.files('dist').joinpath('output.css')) as source:
        destination = Path.cwd() / "src" / "chat-demo-output.css"
        
        if not source.exists():
            print(f"Error: Source file {source} does not exist.")
            return
        
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        print(f"Copied {source} to {destination}")

if __name__ == "__main__":
    main()