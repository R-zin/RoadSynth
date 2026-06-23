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




