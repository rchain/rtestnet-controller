import json
import logging
import os
from asyncio import get_running_loop
from functools import partial
from pathlib import Path

from libcloud.common.google import (
    ResourceNotFoundError, ResourceExistsError, ResourceInUseError,
    InvalidRequestError
)
from libcloud.compute.drivers.gce import GCENodeDriver
from libcloud.dns.drivers.google import GoogleDNSDriver
from libcloud.dns.types import RecordDoesNotExistError
from schema import Schema, SchemaError, Use, And, Or, Optional as Opt

from lib_host import HostClean
from lib_util import run_async, read_json


class HostGCP():
    def __init__(self, config, gcp_credentials_file):
        self.config = config
        creds = read_json(gcp_credentials_file)
        self._compute = GCENodeDriver(
            creds['client_email'],
            gcp_credentials_file,
            project=creds['project_id'],
            datacenter=self.config['gcp_compute_zone'],
            timeout=self.config['compute_timeout']
        )
        self._dns = GoogleDNSDriver(
            creds['client_email'],
            gcp_credentials_file,
            project=creds['project_id']
        )
        self._dns_zone = self._dns.get_zone(config['gcp_dns_zone'])
        self.log = logging.getLogger(__name__ + '.' + self._name)

    @property
    def _name(self):
        return self.config['resources_name']

    async def start(self):
        self.log.info('start() begins')
        try:
            await self._start()
        except:
            self.log.exception('start() failed')
            raise
        self.log.info('start() finished')

    async def _start(self):
        try:
            self.log.info('Creating external static IP address')
            addr = await run_async(self._compute.ex_get_address, self._name)
            self.log.info('Exists')
        except ResourceNotFoundError:
            addr = await run_async(self._compute.ex_create_address, self._name)
            self.log.info('Created')

        self.log.info('External static IP address: %s', addr.address)

        try:
            self.log.info('Creating DNS record: %s', self.config['hostname'])
            await run_async(
                self._dns.create_record, self.config['hostname'],
                self._dns_zone, 'A', {
                    'ttl': self.config['hostname_ttl'],
                    'rrdatas': [addr.address]
                }
            )
            self.log.info('Created')
        except ResourceExistsError:
            self.log.info('Exists')

        try:
            self.log.info('Creating data disk')
            data_disk_name = self._name + '-data'
            data_disk = await run_async(
                self._compute.ex_get_volume, data_disk_name
            )
            self.log.info('Exists')
        except ResourceNotFoundError:
            data_disk = await run_async(
                self._compute.create_volume,
                self.config['data_disk_size'],
                data_disk_name,
                ex_disk_type=(
                    'pd-ssd' if self.config['data_disk_ssd'] else 'pd-standard'
                )
            )
            self.log.info('Created')

        self.log.info(
            'Data disk: %sGB %s', data_disk.size, data_disk.extra['type']
        )

        try:
            self.log.info('Creating host')
            host = await run_async(self._compute.ex_get_node, self._name)
            self.log.info('Exists')
        except ResourceNotFoundError:
            host = await run_async(
                self._compute.create_node,
                self._name,
                location=self.config['gcp_compute_zone'],
                size=self.config['machine_type'],
                image=self.config['boot_image'],
                external_ip=addr,
                ex_network=self.config['gcp_compute_net'],
                ex_subnetwork=self.config['gcp_compute_subnet'],
            )
            self.log.info('Created')

        self.log.info('Host: %s %s', host.extra['image'], host.size)

        try:
            self.log.info('Attaching data disk')
            await run_async(
                self._compute.attach_volume,
                host,
                data_disk,
                ex_auto_delete=False
            )
            self.log.info('Attached')
        except ResourceInUseError:
            self.log.info('Already attached')

        self.log.info('Setting host tags')
        await run_async(
            self._compute.ex_set_node_tags, host,
            self.config['gcp_compute_tags']
        )

        self.log.info('Setting host metadata')
        await run_async(
            self._compute.ex_set_node_metadata, host,
            self.config['host_metadata']
        )

        self.log.info('Starting host')
        await run_async(self._compute.ex_start_node, host)
        self.log.info('Started')

    async def stop(self, clean=HostClean.STOP) -> None:
        self.log.info('stop(clean=%s) begins', clean.name)
        try:
            await self._stop(clean)
        except:
            self.log.exception('stop() failed')
            raise
        self.log.info('stop() finished')

    async def _stop(self, clean) -> None:
        try:
            self.log.info('Stopping host')
            host = await run_async(
                self._compute.ex_get_node, self._name,
                self.config['gcp_compute_zone']
            )
            await run_async(self._compute.ex_stop_node, host)
            self.log.info('Stopped')

            if clean <= HostClean.STOP:
                return

            self.log.info('Removing host')
            await run_async(
                self._compute.destroy_node, host, destroy_boot_disk=True
            )
            self.log.info('Removed')

        except ResourceNotFoundError:
            self.log.info('Not present')

        if clean <= HostClean.HOST:
            return

        try:
            self.log.info('Removing data disk')
            data_disk_name = self._name + '-data'
            data_disk = await run_async(
                self._compute.ex_get_volume, data_disk_name
            )
            await run_async(self._compute.destroy_volume, data_disk)
            self.log.info('Removed')
        except ResourceNotFoundError:
            self.log.info('Not present')

        if clean <= HostClean.DATA:
            return

        try:
            self.log.info('Removing DNS record')
            record = await run_async(
                self._dns.get_record, self._dns_zone.id,
                'A:' + self.config['hostname']
            )
            await run_async(self._dns.delete_record, record)
            self.log.info('Removed')
        except RecordDoesNotExistError:
            self.log.info('Not present')

        try:
            self.log.info('Removing external static IP address')
            await run_async(self._compute.ex_destroy_address, self._name)
            self.log.info('Removed')
        except ResourceNotFoundError:
            self.log.info('Not present')
