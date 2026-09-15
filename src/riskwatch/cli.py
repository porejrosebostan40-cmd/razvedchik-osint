import json
from .runner import run

def main():
    print(json.dumps(run(),ensure_ascii=False,indent=2))

if __name__=='__main__': main()
