"""Author: Michal Zmuda
Copyright (C) 2015 ACK CYFRONET AGH
This software is released under the MIT license cited in 'LICENSE.txt'

Brings up a set of oneprovider worker nodes. They can create separate clusters.
"""

import os
import subprocess
import sys
from . import common, docker, worker, gui


def up(image, bindir, dns_server, uid, config_path, logdir=None,
       storages_dockers=None):
    return worker.up(image, bindir, dns_server, uid, config_path,
                     ProviderWorkerConfigurator(), logdir,
                     storages_dockers=storages_dockers)


class ProviderWorkerConfigurator:
    def tweak_config(self, cfg, uid, instance):
        sys_config = cfg['nodes']['node']['sys.config'][self.app_name()]
        if 'oz_domain' in sys_config:
            oz_hostname = worker.cluster_domain(sys_config['oz_domain'], uid)
            sys_config['oz_domain'] = oz_hostname
        sys_config['interprovider_connections_security'] = 'only_verify_peercert'
        # required for op-worker to init connection to Onezone as onepanel 
        # that normally synchronizes clocks is not started in env_up
        sys_config['graph_sync_require_clock_sync_for_connection'] = False
        return cfg

    def pre_start_commands(self, domain):
        return 'escript bamboos/gen_dev/gen_dev.escript /tmp/gen_dev_args.json'

    # Called BEFORE the instance (cluster of workers) is started,
    # once for every instance
    def pre_configure_instance(self, instance, instance_domain, config):
        this_config = config[self.domains_attribute()][instance]
        if 'gui_override' in this_config and isinstance(
                this_config['gui_override'], dict):
            # Preconfigure GUI override
            gui_config = this_config['gui_override']
            gui.override_gui(gui_config, instance_domain)

    # Called AFTER the instance (cluster of workers) has been started
    def post_configure_instance(self, bindir, instance, config, container_ids,
                                output, storages_dockers=None):
        this_config = config[self.domains_attribute()][instance]
        # Check if gui livereload is enabled in env and turn it on
        if 'gui_override' in this_config and isinstance(
                this_config['gui_override'], dict):
            gui_config = this_config['gui_override']
            livereload_flag = gui_config['livereload']
            if livereload_flag:
                for container_id in container_ids:
                    livereload_dir = gui_config['mount_path']
                    gui.run_livereload(container_id, livereload_dir)
        if 'os_config' in this_config:
            os_config = this_config['os_config']
            create_storages(config['os_configs'][os_config]['storages'],
                            output[self.nodes_list_attribute()],
                            this_config[self.app_name()], bindir,
                            storages_dockers)

    def extra_volumes(self, config, bindir, instance, storages_dockers):
        if 'os_config' in config and config['os_config']['storages']:
            if isinstance(config['os_config']['storages'][0], str):
                posix_storages = config['os_config']['storages']
            else:
                posix_storages = []
                for s in config['os_config']['storages']:
                    if s['type'] == 'posix' and 'group' in s:
                        posix_storages.append({
                            'name': s['name'],
                            'readonly': s.get('readonly', False),
                            'group': s['group']
                        })
                    elif s['type'] == 'posix':
                        posix_storages.append({
                            'name': s['name'],
                            'readonly': s.get('readonly', False)
                        })
        else:
            posix_storages = []

        extra_volumes = []
        grouped_storages = {}

        for s in posix_storages:
            if not storages_dockers:
                storages_dockers = {'posix': {}}
            name = s['name']
            readonly = s['readonly']
            if name not in list(storages_dockers['posix'].keys()):
                if 'group' in s and s['group'] in grouped_storages:
                    (host_path, docker_path, mode) = (grouped_storages[s['group']], name, 'ro' if readonly else 'rw')
                elif 'group' in s:
                    (host_path, docker_path, mode) = common.volume_for_storage(name, readonly)
                    grouped_storages[s['group']] = host_path
                else:
                    (host_path, docker_path, mode) = common.volume_for_storage(name, readonly)

                v = (host_path, docker_path, mode)
                storages_dockers['posix'][name] = {
                    "host_path": host_path,
                    "docker_path": docker_path,
                    "mode": mode
                }
            else:
                d = storages_dockers['posix'][name]
                v = (d['host_path'], d['docker_path'], d['mode'])
            extra_volumes.append(v)

        # Check if gui override is enabled in env and add required volumes
        if 'gui_override' in config and isinstance(config['gui_override'],
                                                   dict):
            gui_config = config['gui_override']
            extra_volumes.extend(gui.extra_volumes(gui_config, instance))
        return extra_volumes

    def couchbase_ramsize(self):
        return 1024

    def couchbase_buckets(self):
        return {"onedata": 1024}

    def app_name(self):
        return "op_worker"

    def domains_attribute(self):
        return "provider_domains"

    def domain_env_name(self):
        return "test_web_cert_domain"

    def nodes_list_attribute(self):
        return "op_worker_nodes"

    def has_dns_server(self):
        return False

    def ready_check(self, container):
        ip = docker.inspect(container)['NetworkSettings']['IPAddress']
        return common.nagios_up(ip, '443', 'https')


def create_storages(storages, op_nodes, op_config, bindir, storages_dockers):
    # copy escript to docker host
    script_names = {'posix': 'create_posix_storage.escript',
                    's3': 'create_s3_storage.escript',
                    'ceph': 'create_ceph_storage.escript',
                    'cephrados': 'create_cephrados_storage.escript',
                    'swift': 'create_swift_storage.escript',
                    'glusterfs': 'create_glusterfs_storage.escript',
                    'webdav': 'create_webdav_storage.escript',
                    'xrootd': 'create_xrootd_storage.escript',
                    'nfs': 'create_nfs_storage.escript',
                    'http': 'create_http_storage.escript',
                    'nulldevice': 'create_nulldevice_storage.escript'}
    pwd = common.get_script_dir()
    for script_name in list(script_names.values()):
        command = ['cp', os.path.join(pwd, script_name),
                   os.path.join(bindir, script_name)]
        subprocess.check_call(command)
    # execute escript on one of the nodes
    # (storage is common fo the whole provider)
    first_node = op_nodes[0]
    container = first_node.split("@")[1]
    worker_name = container.split(".")[0]
    cookie = op_config[worker_name]['vm.args']['setcookie']
    bindir = os.path.abspath(bindir)
    script_paths = dict(
        [(k_v[0], os.path.join(bindir, k_v[1])) for k_v in iter(script_names.items())])
    for storage in storages:
        if isinstance(storage, str):
            storage = {'type': 'posix', 'name': storage}
        if storage['type'] in ['posix']:
            st_path = storage['name']
            command = ['escript', script_paths['posix'], cookie,
                       first_node, storage['name'], st_path,
                       'canonical']
            assert 0 == docker.exec_(container, command, tty=True,
                                     stdout=sys.stdout, stderr=sys.stderr)
        elif storage['type'] == 'ceph':
            config = storages_dockers['ceph'][storage['name']]
            pool = storage['pool'].split(':')[0]
            command = ['escript', script_paths['ceph'], cookie,
                       first_node, storage['name'], 'ceph',
                       config['host_name'], pool, config['username'],
                       config['key'], 'flat']
            assert 0 == docker.exec_(container, command, tty=True,
                                     stdout=sys.stdout, stderr=sys.stderr)
        elif storage['type'] == 'cephrados':
            config = storages_dockers['cephrados'][storage['name']]
            pool = storage['pool'].split(':')[0]
            command = ['escript', script_paths['cephrados'], cookie,
                       first_node, storage['name'], 'ceph',
                       config['host_name'], pool, config['username'],
                       config['key'], storage.get('block_size', '10485760'),
                       storage.get('storage_path_type', 'flat')]
            assert 0 == docker.exec_(container, command, tty=True,
                                     stdout=sys.stdout, stderr=sys.stderr)
        elif storage['type'] == 's3':
            config = storages_dockers['s3'][storage['name']]
            command = ['escript', script_paths['s3'], cookie,
                       first_node, storage['name'], config['host_name'],
                       config.get('scheme', 'http'), storage['bucket'],
                       config['access_key'], config['secret_key'],
                       storage.get('block_size', '10485760'),
                       storage.get('storage_path_type', 'flat')]
            assert 0 == docker.exec_(container, command, tty=True,
                                     stdout=sys.stdout, stderr=sys.stderr)
        elif storage['type'] == 'swift':
            config = storages_dockers['swift'][storage['name']]
            command = ['escript', script_paths['swift'], cookie,
                       first_node, storage['name'],
                       'http://{0}:{1}/v3'.format(
                           config['host_name'], config['keystone_port']),
                       storage['container'], config['project_name'],
                       config['user_name'], config['password'],
                       storage.get('block_size', '10485760'),
                       storage.get('storage_path_type', 'flat')]
            assert 0 == docker.exec_(container, command, tty=True,
                                     stdout=sys.stdout, stderr=sys.stderr)
        elif storage['type'] == 'glusterfs':
            config = storages_dockers['glusterfs'][storage['name']]
            command = ['escript', script_paths['glusterfs'], cookie,
                       first_node, storage['name'], storage['volume'],
                       config['host_name'], str(config['port']),
                       storage['transport'], storage['mountpoint'],
                       'cluster.write-freq-threshold=100;', 'canonical']
            assert 0 == docker.exec_(container, command, tty=True,
                                     stdout=sys.stdout, stderr=sys.stderr)
        elif storage['type'] == 'nfs':
            config = storages_dockers['nfs'][storage['name']]
            command = ['escript', script_paths['nfs'], cookie,
                       first_node, storage['name'], storage['version'],
                       storage['volume'], config['host'], 'canonical']
            assert 0 == docker.exec_(container, command, tty=True,
                                     stdout=sys.stdout, stderr=sys.stderr)
        elif storage['type'] == 'webdav':
            config = storages_dockers['webdav'][storage['name']]
            command = ['escript', script_paths['webdav'], cookie,
                       first_node, storage['name'], config['endpoint'],
                       config.get('credentials_type', 'basic'),
                       config['credentials'], 'false',
                       storage.get('authorization_header', ''),
                       storage.get('range_write_support', 'sabredav'),
                       storage.get('connection_pool_size', '10'),
                       storage.get('maximum_upload_size', '0'),
                       'canonical']
            assert 0 == docker.exec_(container, command, tty=True,
                                     stdout=sys.stdout, stderr=sys.stderr)
        elif storage['type'] == 'xrootd':
            config = storages_dockers['xrootd'][storage['name']]
            command = ['escript', script_paths['xrootd'], cookie,
                       first_node, storage['name'], config['url'],
                       config.get('credentials_type', 'none'),
                       config.get('credentials', ''), 'canonical']
            assert 0 == docker.exec_(container, command, tty=True,
                                     stdout=sys.stdout, stderr=sys.stderr)
        elif storage['type'] == 'http':
            config = storages_dockers['http'][storage['name']]
            command = ['escript', script_paths['http'], cookie,
                       first_node, storage['name'], config['endpoint'],
                       config.get('credentials_type', 'basic'),
                       config['credentials'], 'false',
                       storage.get('authorization_header', ''),
                       storage.get('connection_pool_size', '10'),
                       'canonical']
            assert 0 == docker.exec_(container, command, tty=True,
                                     stdout=sys.stdout, stderr=sys.stderr)
        elif storage['type'] == 'nulldevice':
            command = ['escript', script_paths['nulldevice'], cookie,
                       first_node, storage['name'], storage['latencyMin'],
                       storage['latencyMax'], storage['timeoutProbability'],
                       storage['filter'],
                       storage['simulatedFilesystemParameters'],
                       storage['simulatedFilesystemGrowSpeed'],
                       'canonical']
            assert 0 == docker.exec_(container, command, tty=True,
                                     stdout=sys.stdout, stderr=sys.stderr)
        else:
            raise RuntimeError(
                'Unknown storage type: {}'.format(storage['type']))
    # clean-up
    for script_name in list(script_names.values()):
        command = ['rm', os.path.join(bindir, script_name)]
        subprocess.check_call(command)
