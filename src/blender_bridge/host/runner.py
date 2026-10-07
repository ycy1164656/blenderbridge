"""Private detached Host runner entry point."""
import json
from pathlib import Path
import sys
from .storage import Store
from .jobs import HostJobs


def main():
    data=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    result=HostJobs(Store(data['root'],data['config'])).run(data['id'])
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
