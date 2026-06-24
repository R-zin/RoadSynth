import asyncio
import shutil
import os
from typing import List
from typing import Optional

_SUMO_TOOL_DIRS = [
    "/usr/share/sumo/tools",
    "/usr/local/share/sumo/tools",
]

def find_binary(names:List[str]) -> Optional[str]:
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None

def find_sumo_script(filename:str)->Optional[str]:
    sumo_home = os.environ.get("SUMO_HOME","")
    candidates = [*[f"{d}/{filename}" for d in _SUMO_TOOL_DIRS],
                  f"{sumo_home}/bin/sumo" if sumo_home else None]
    return next((c for c in candidates if os.path.exists(c)), None)


async def run_async(cmd:List[str],workdir:Path,timeout:float=600.0):
    try:
        process = await asyncio.create_subprocess_exec(*cmd,
                                                       stdout=asyncio.subprocess.PIPE,
                                                       stderr=asyncio.subprocess.PIPE,
                                                       cwd=str(workdir))
    except FileNotFoundError:
        raise RuntimeError("File not found")

    try:
        raw_out,raw_err = await asyncio.wait_for(process.communicate(),timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        raise RuntimeError("Timed out")
    return process.returncode,raw_out.decode("replace"),raw_err.decode("replace")




