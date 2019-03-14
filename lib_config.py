import os
import os.path
from pathlib import Path

import pyjq
from schema import Schema, And, Use, Optional as Opt

NonEmptyStr = And(str, len)
ConfigDict = {Opt(str): object}
PositiveNum = Use(int, lambda i: i >= 0)
OptEnv = lambda name, env_name: Opt(name, default=lambda: os.environ[env_name])


def add_missing_value(config, path, value):
    if pyjq.first(path, config) == None:
        v = value() if callable(value) else value
        config = pyjq.first(path + '=$v', config, vars={'v': v})
    return config


def add_missing_value_aux(config, config_aux, path, value):
    get_script = pyjq.compile(path)
    if get_script.first(config) == None:
        aux_val = get_script.first(config_aux)
        if aux_val != None:
            v = aux_val
        else:
            v = value() if callable(value) else value
        set_script = pyjq.compile(path + '=$v', vars={'v': v})
        config = set_script.first(config)
        if aux_val == None:
            config_aux = set_script.first(config_aux)
    return config, config_aux
