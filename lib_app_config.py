import copy
import os.path
import shutil
from pathlib import Path

from schema import Schema, Use, Optional as Opt

from lib_config import (
    ConfigDict, NonEmptyStr, PositiveNum, OptEnv, add_missing_value
)
from lib_util import read_json

SCHEMA = Schema(
    { # yapf: disable
        'data_dir': NonEmptyStr,
        OptEnv('gcp_credentials_file', ' GOOGLE_APPLICATION_CREDENTIALS'): os.path.isfile,
        Opt('initial_delay'): PositiveNum,
        Opt('check_interval'): PositiveNum
    }
)


class AppConfig:
    def __init__(self, data):
        data = copy.deepcopy(data)
        self.data = SCHEMA.validate(data)

    def _get(self, key, default):
        try:
            return self.data[key]
        except KeyError:
            return default() if callable(default) else default

    def _get_path(self, key, default=None):
        path = self._get(key, default) if default else self.data[key]
        return os.path.abspath(path)

    @property
    def data_dir(self):
        return self.data['data_dir']

    @property
    def gcp_credentials_file(self) -> str:
        return self._get_path('gcp_credentials_file')

    @property
    def node_config_global(self):
        return self._get('node_config_global', {})

    @property
    def nodes_data_dir(self) -> str:
        return self._get_path(
            'nodes_data_dir',
            lambda: os.path.join(self.data_dir, 'nodes'),
        )

    @property
    def node_config_templates_dir(self) -> str:
        return self._get_path(
            'node_config_templates_dir',
            lambda: os.path.join(self.data_dir, 'templates'),
        )

    @property
    def initial_delay(self) -> int:
        return self._get('initial_delay', 600)

    @property
    def check_interval(self) -> int:
        return self._get('check_interval', 120)
