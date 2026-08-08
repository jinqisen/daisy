import signal
import sys
import pydantic
from contextlib import contextmanager

def apply_patches():
    """
    Minimal patches required for compatibility.
    """
    # 1. Patch langchain_core.pydantic_v1
    try:
        if 'langchain_core.pydantic_v1' not in sys.modules:
            if hasattr(pydantic, 'v1'):
                sys.modules['langchain_core.pydantic_v1'] = pydantic.v1
            else:
                from pydantic import v1
                sys.modules['langchain_core.pydantic_v1'] = v1
    except Exception as e:
        print(f"Warning: Failed to patch langchain_core.pydantic_v1: {e}")

    # 2. Windows specific patches for Signal
    if sys.platform == "win32":
        missing_signals = [
            "SIGHUP", "SIGQUIT", "SIGKILL", "SIGUSR1", "SIGUSR2", 
            "SIGPIPE", "SIGALRM", "SIGTSTP", "SIGCONT", "SIGCHLD"
        ]
        
        for sig in missing_signals:
            if not hasattr(signal, sig):
                setattr(signal, sig, 99)

