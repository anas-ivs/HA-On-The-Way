import os
import re

def read_version() -> str:
    """Read the add-on version from config.yaml (single source of truth).
    Checks the container path (/app/config.yaml) and the dev layout (../config.yaml)."""
    here = os.path.dirname(__file__)
    for path in (os.path.join(here, "config.yaml"),
                 os.path.join(here, "..", "config.yaml")):
        try:
            with open(path) as f:
                m = re.search(r'^version:\s*"?([^"\s]+)"?', f.read(), re.MULTILINE)
                if m:
                    return m.group(1)
        except OSError:
            continue
    return "unknown"

VERSION = read_version()
