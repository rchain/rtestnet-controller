import enum
import functools
import logging
import os
import os.path
import pprint
import time
import uuid
from asyncio import (
    Task, Lock, CancelledError, create_task, create_subprocess_exec
)
from pathlib import Path
from subprocess import DEVNULL, CalledProcessError

from deepmerge import always_merger as merger

import lib_rchain_key
import lib_rnode_tls
from lib_config import add_missing_value, add_missing_value_aux
from lib_host import HostClean
from lib_host_gcp import HostGCP
from lib_util import (
    run_async, resolve_path, write_json, read_json, try_read_json
)

NodeFailure = enum.Enum(
    'NodeFailure', '''
    TIMEOUT_HEARTBEAT
    TIMEOUT_START_RNODE
    TIMEOUT_START_HOST
'''
)


class NodeContextError(Exception):
    pass


class NodeContext:
    def __init__(self, app_config, data_dir, name, config_user=None):
        self.app_config = app_config
        self.data_dir = Path(data_dir).resolve()
        self.name = name

        self.host_up = False
        self.genesis = None
        self.follows = None
        self.ts_start = 0
        self.ts_heartbeat = 0
        self.failure = None

        self.log = logging.getLogger(__name__ + '.' + name)
        self.maintenance_lock = Lock()

        self.cookie_exec = None
        self.cookie_data = None

        self.load_config(config_user)
        self.host = HostGCP(self.config, self.app_config.gcp_credentials_file)

    def __str__(self):
        return (
            'NodeContext(' + self.name + \
            (' up=' + ('1' if self.host_up else '0')) + \
            (' fail=' + self.failure.name if self.failure else '') + \
            (' ts_start=' + str(int(self.ts_start))) + \
            (' ts_heartbeat=' + str(int(self.ts_heartbeat))) + \
            (' follows=' + self.follows.name if self.follows else ' leader') + \
            (' genesis=' + self.genesis if self.genesis else '') + \
            ')'
        )

    __repr__ = __str__

    def gen_cookie_exec(self):
        self.cookie_exec = uuid.uuid4()

    def gen_cookie_data(self):
        self.cookie_data = uuid.uuid4()

    # properties {{{

    @property
    def config_skeleton(self):
        return {
            'rnode_conf':
                {
                    'server': {
                        'port': 40400,
                        'port-kademlia': 40404
                    },
                    'grpc': {
                        'port-external': 40401
                    }
                },
            'hostname_suffix': '.',
            'hostname_ttl': 300,
            'resources_name_prefix': '',
            'templates': [],
            'timeout_heartbeat': 300,
            'timeout_start_rnode': 300,
            'timeout_start_host': 300,
            'host_metadata': {},
            'compute_timeout': 600,
        }

    @property
    def files_dir(self) -> Path:
        return self.data_dir / 'files'

    @property
    def config_file_user(self) -> Path:
        return self.data_dir / 'config.user.json'

    @property
    def config_file_auxiliary(self) -> Path:
        return self.data_dir / 'config.aux.json'

    @property
    def config_file_full(self) -> Path:
        return self.data_dir / 'config.full.json'

    @property
    def rnode_conf_file(self) -> Path:
        return self.files_dir / 'rnode.conf'

    @property
    def rnode_tls_key_file(self) -> Path:
        return self.files_dir / 'node.key.pem'

    # }}}

    # configuration {{{

    def load_config_template(self, name):
        try:
            path = resolve_path(
                self.app_config.node_config_templates_dir, name + '.json'
            )
            return read_json(path)
        except FileNotFoundError:
            raise NodeContextError(f'Template "{name}" does not exist')

    def load_config_merged(self, config_user):
        config = {}

        merge_list = [
            config_user,
            self.app_config.node_config_global,
            self.config_skeleton,
        ]
        merged_templates = set()

        i = 0
        while i < len(merge_list):
            for tpl_name in merge_list[i].get('templates', []):
                if not tpl_name in merged_templates:
                    tpl = self.load_config_template(tpl_name)
                    merge_list.insert(i + 1, tpl)
                    merged_templates.add(tpl_name)
            i += 1

        for part in merge_list[::-1]:
            config = merger.merge(config, part)

        return config

    def load_config_full(self, config_user):
        config = self.load_config_merged(config_user)
        config_aux = try_read_json(self.config_file_auxiliary, {})

        config, config_aux = add_missing_value_aux(
            config,
            config_aux,
            '.rnode_conf.casper."validator-private-key"',
            lambda: lib_rchain_key.generate_key_hex(),
        )

        config, config_aux = add_missing_value_aux(
            config,
            config_aux,
            '.rnode_tls_key',
            lambda: lib_rnode_tls.generate_key_pem(),
        )

        config = add_missing_value(
            config,
            '.rnode_id',
            lambda: lib_rnode_tls.get_node_id(config['rnode_tls_key']),
        )

        config = add_missing_value(
            config,
            '.resources_name',
            lambda: config['resources_name_prefix'] + self.name,
        )

        config = add_missing_value(
            config,
            '.hostname',
            lambda: self.name + config['hostname_suffix'],
        )

        if not config['hostname'].endswith('.'):
            config['hostname'] += '.'

        config = add_missing_value(
            config,
            '.rnode_addr',
            lambda: 'rnode://{}@{}?protocol={}&discovery={}'.format(
                config['rnode_id'],
                config['hostname'],
                config['rnode_conf']['server']['port'],
                config['rnode_conf']['server']['port-kademlia'],
            ),
        )

        return config, config_aux

    def load_update_config(self, config_user=None):
        if config_user == None:
            config_user = try_read_json(self.config_file_user, {})
        config, config_aux = self.load_config_full(config_user)

        os.makedirs(self.data_dir, exist_ok=True)
        if config_user:
            write_json(self.config_file_user, config_user)
        write_json(self.config_file_auxiliary, config_aux)
        write_json(self.config_file_full, config)

        os.makedirs(self.files_dir, exist_ok=True)
        write_json(self.rnode_conf_file, config['rnode_conf'])
        self.rnode_tls_key_file.write_text(config['rnode_tls_key'])

        self.config = config
        self.gen_cookie_exec()

    def load_config(self, config_user=None):
        if config_user == None and self.config_file_full.exists():
            self.config = read_json(self.config_file_full)
        else:
            self.load_update_config(config_user)

    # }}}

    # lifecycle {{{

    async def _stop(self, clean):
        self.host_up = False
        self.failure = None
        self.log.info('Stopping')
        await self.host.stop(clean)
        self.log.info('Stopped')

    async def _start(self):
        self.log.info('Starting')
        await self.host.start()
        if not self.host_up:
            self.ts_start = time.time()
        self.log.info('Started')

    async def _try_start(self):
        try:
            if self.maintenance_lock.locked():
                return
            async with self.maintenance_lock:
                await self._start()
        except:
            self.log.exception('Start failed')
            raise

    async def _try_restart(self, clean):
        try:
            if self.maintenance_lock.locked():
                return
            async with self.maintenance_lock:
                skip_start = False
                try:
                    await self._stop(clean)
                except CancelledError:
                    skip_start = True
                    raise
                finally:
                    if not skip_start:
                        await self._start()
        except:
            self.log.exception('Restart failed')
            raise

    def try_start_async(self):
        self.log.info('Scheduling start')
        create_task(self._try_start())

    def try_restart_async(self, clean_data=False):
        self.log.info('Scheduling restart')
        clean = HostClean.DATA if clean_data else HostClean.STOP
        create_task(self._try_restart(clean))

    # }}}

    def heartbeat(self, msg):
        self.log.info('Received heartbeat message')

        if self.maintenance_lock.locked():
            self.log.info('Ignoring due to active maintenance')
            return {}

        now = time.time()
        if not self.host_up:
            self.log.info('Host is up')
            self.host_up = True
            self.ts_start = now
        self.ts_heartbeat = now

        if 'cookie_exec' in msg and not self.cookie_exec:
            self.cookie_exec = msg['cookie_exec']

        if 'cookie_data' in msg and not self.cookie_data:
            self.cookie_data = msg['cookie_data']

        if 'genesis' in msg and self.genesis != msg['genesis']:
            self.genesis = msg['genesis']

        reply = {
            'cookie_exec': self.cookie_exec,
            'cookie_data': self.cookie_data,
            'rnode_package_url': self.config['rnode_package_url']
        }

        if self.follows:
            reply['mode'] = 'follower'
            reply['leader'] = self.follows.config['rnode_addr']
        else:
            reply['mode'] = 'leader'

        self.log.info('Sending reply')
        if self.log.isEnabledFor(logging.INFO):
            for k in sorted(reply.keys()):
                self.log.info('  reply[%s] = %s', k, reply[k])

        return reply

    def _check_timeouts(self, ts):
        if (
            self.host_up and
            ts > self.ts_heartbeat + self.config['timeout_heartbeat']
        ):
            return NodeFailure.TIMEOUT_HEARTBEAT
        if (
            self.host_up and not self.genesis and
            ts > self.ts_start + self.config['timeout_start_rnode']
        ):
            return NodeFailure.TIMEOUT_START_RNODE
        if (
            not self.host_up and
            ts > self.ts_start + self.config['timeout_start_host']
        ):
            return NodeFailure.TIMEOUT_START_HOST
        return None

    def check_failure(self, ts):
        if self.maintenance_lock.locked():
            return None
        if not self.failure:
            new_failure = self._check_timeouts(ts)
            if new_failure:
                self.log.info('Failure: %s', new_failure.name)
                self.failure = new_failure
        return self.failure
