from typing import Tuple

def gpu_ids_string2tuple(
        gpu_ids: str
    ) -> Tuple:
    """Convert GPU  ID input from colon spaced (1:2:3) to no space inbetween GPU IDs (123)"""
    gpu_ids = gpu_ids.replace(' ','')
    return tuple(map(int,gpu_ids.replace(':','')))
