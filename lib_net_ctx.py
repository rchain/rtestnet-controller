import logging
import os
import os.path
import random
import time
from asyncio import Task, Lock, create_task, sleep
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from itertools import groupby
from types import SimpleNamespace

import lib_app_config
import lib_node_ctx
from lib_util import *


class NetworkContext:
    def __init__(self, config):
        self.config = config

        self.nodes = {}
        self.leader = None

        self.log = logging.getLogger(__name__)

    def create_node(self, name, config_user=None):
        try:
            self.log.info('Creating node %s', name)
            node = lib_node_ctx.NodeContext(
                self.config,
                os.path.join(self.config.nodes_data_dir, name),
                name,
                config_user,
            )
            self.nodes[name] = node
            node.try_start_async()
            self.log.info('Created')
        except:
            self.log.exception('Failed to create node')
            raise

    async def run(self):
        for d in [
            self.config.nodes_data_dir,
            self.config.node_config_templates_dir,
        ]:
            os.makedirs(d, exist_ok=True)
        for name in os.listdir(self.config.nodes_data_dir):
            self.create_node(name)
        try:
            await sleep(self.config.initial_delay)
            await self.main_loop()
        except:
            self.log.exception('Main loop failed')
            raise

    async def main_loop(self):
        while True:
            #import asyncio
            #self.log.info('Running async tasks:')
            #for t in asyncio.all_tasks():
            #    self.log.info('  %s', t)

            self.pick_majority()
            await sleep(self.config.check_interval)

    def pick_majority(self):
        now = time.time()
        groups_map = defaultdict(list)

        for node in self.nodes.values():
            failure = node.check_failure(now)
            if failure:
                self.log.warn('Node has failure: %s', node)
                node.try_restart_async()
                continue
            if node.genesis:
                groups_map[node.genesis].append(node)

        if groups_map:
            groups = sorted(groups_map.values(), key=len, reverse=True)
            major_groups = list(next(groupby(groups, len))[1])

            if self.log.isEnabledFor(logging.INFO):
                self.log.info('Existing genesis blocks (hash / # nodes):')
                for g in groups:
                    self.log.info('  %s %d', g[0].genesis, len(g))

            if self.leader:
                for group in major_groups:
                    if self.leader in group:
                        break
                else:
                    self.leader = None

            if not self.leader:
                self.leader = random.choice(random.choice(major_groups))
                self.leader.follows = None
                self.log.info('Picked new leader: %s', self.leader)
            else:
                self.log.info('Retained leader: %s', self.leader)

            for node in self.nodes.values():
                if node == self.leader:
                    continue
                if node.genesis not in [self.leader.genesis, None]:
                    self.log.info('Node has invalid genesis: %s', node)
                    node.genesis = None
                    node.follows = self.leader
                    node.try_restart_async(clean_data=True)
                elif node.follows != self.leader:
                    self.log.info('Node follows wrong leader: %s', node)
                    node.follows = self.leader
                    node.try_restart_async()
        else:
            self.log.info('There are no genesis blocks')
