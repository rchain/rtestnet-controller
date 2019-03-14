import asyncio
import functools
import json

from pathlib import Path
from typing import Union


def run_async(func, *args, **kwargs):
    no_args_func = functools.partial(func, *args, **kwargs)
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(None, no_args_func)


def read_json(path):
    with open(path, 'r') as f:
        return json.load(f)


def try_read_json(path, default=None):
    try:
        return read_json(path)
    except FileNotFoundError:
        return default


def write_json(path, obj):
    with open(path, 'w') as f:
        config = json.dump(obj, f, sort_keys=True, indent=4)


# credits: https://stackoverflow.com/q/22749882/214720
def resolve_path(dir_path: Union[Path, str], filename: str) -> Path:
    if not isinstance(dir_path, Path):
        dir_path = Path(dir_path)
    file_path = dir_path / filename
    file_path.resolve()
    if dir_path not in file_path.parents:
        raise ValueError('Invalid filename: "%s"'.format(filename))
    return file_path
