"""Author: Konrad Zemek, Michal Zmuda
Copyright (C) 2015 ACK CYFRONET AGH
This software is released under the MIT license cited in 'LICENSE.txt'

Brings up a set of worker nodes. They can create separate clusters.
Script is parametrised by worker type related configurator.
"""

import copy
import json
import os
from . import common, docker, couchbase, dns, cluster_manager, test_ca
from .timeouts import *


def cluster_domain(instance, uid):
    """Formats domain for a cluster."""
    return common.format_hostname(instance, uid)


def worker_hostname(node_name, instance, uid):
    """Formats hostname for a docker hosting cluster_worker.
    NOTE: Hostnames are also used as docker names!
    """
    return common.format_hostname([node_name, instance], uid)


def worker_erl_node_name(node_name, instance, uid):
    """Formats erlang node name for a vm on cluster_worker docker.
    """
    hostname = worker_hostname(node_name, instance, uid)
    return common.format_erl_node_name('worker', hostname)


def _tweak_config(config, name, instance, uid, configurator, docker_host=None):
    cfg = copy.deepcopy(config)
    cfg['nodes'] = {'node': cfg['nodes'][name]}
    app_name = configurator.app_name()
    sys_config = cfg['nodes']['node']['sys.config']
    sys_config[app_name]['cm_nodes'] = [
        cluster_manager.cm_erl_node_name(n, instance, uid) for n in
        sys_config[app_name]['cm_nodes']]
    # Set the cluster domain (needed for nodes to start)
    sys_config[app_name][configurator.domain_env_name()] = {
        'string': cluster_domain(instance, uid)
    }

    if 'cluster_worker' not in sys_config:
        sys_config['cluster_worker'] = dict()
    sys_config['cluster_worker'][
        'persistence_driver_module'] = _db_driver_module(cfg['db_driver'])

    if 'vm.args' not in cfg['nodes']['node']:
        cfg['nodes']['node']['vm.args'] = {}
    vm_args = cfg['nodes']['node']['vm.args']
    vm_args['name'] = worker_erl_node_name(name, instance, uid)

    cfg = configurator.tweak_config(cfg, uid, instance)
    return cfg, sys_config[app_name]['db_nodes']


def _node_up(image, bindir, dns_servers, config, db_node_mappings, logdir,
             configurator, storages_dockers):
    app_name = configurator.app_name()
    node_name = config['nodes']['node']['vm.args']['name']
    db_nodes = config['nodes']['node']['sys.config'][app_name]['db_nodes']

    for i in range(len(db_nodes)):
        db_nodes[i] = db_node_mappings[db_nodes[i]]

    (name, sep, hostname) = node_name.partition('@')
    (_, _, domain) = hostname.partition('.')

    bindir = os.path.abspath(bindir)

    key, cert, cacert = test_ca.generate_webcert(domain)

    command = '''set -e
mkdir -p /root/bin/node/log/
mkdir -p /root/bin/node/etc/certs
mkdir -p /root/bin/node/etc/cacerts
bindfs --create-for-user={uid} --create-for-group={gid} /root/bin/node/log /root/bin/node/log
cat <<"EOF" > /tmp/gen_dev_args.json
{gen_dev_args}
EOF
cat <<"EOF" > /root/bin/node/etc/certs/web_key.pem
{key}
EOF
cat <<"EOF" > /root/bin/node/etc/certs/web_cert.pem
{cert}
EOF
cat <<"EOF" > /root/bin/node/etc/certs/web_chain.pem
{cacert}
EOF
cat <<"EOF" > /root/bin/node/etc/cacerts/OneDataTestWebServerCa.pem
{cacert}
EOF
{pre_start_commands}
ln -s {bindir} /root/build
/root/bin/node/bin/{executable} console'''

    pre_start_commands = configurator.pre_start_commands(domain)
    command = command.format(
        bindir=bindir,
        gen_dev_args=json.dumps({configurator.app_name(): config}),
        key=key,
        cert=cert,
        cacert=cacert,
        pre_start_commands=pre_start_commands,
        uid=os.geteuid(),
        gid=os.getegid(),
        executable=configurator.app_name()
    )

    volumes = ['/root/bin', (bindir, bindir, 'ro')]
    volumes += configurator.extra_volumes(config, bindir, domain,
                                          storages_dockers)

    if logdir:
        logdir = os.path.join(os.path.abspath(logdir), hostname)
        os.makedirs(logdir)
        volumes.extend([(logdir, '/root/bin/node/log', 'rw')])

    container = docker.run(
        image=image,
        name=hostname,
        hostname=hostname,
        detach=True,
        interactive=True,
        tty=True,
        workdir=bindir,
        volumes=volumes,
        dns_list=dns_servers,
        privileged=True,
        command=command)

    # create system users and groups (if specified)
    if 'os_config' in config:
        common.create_users(container, config['os_config']['users'])
        common.create_groups(container, config['os_config']['groups'])

    return container, {
        'docker_ids': [container],
        configurator.nodes_list_attribute(): [node_name]
    }


def _couchbase_up(cluster_name, db_nodes, dns_servers, uid, configurator,
                  docker_host=None):
    db_node_mappings = {}
    for node in db_nodes:
        db_node_mappings[node] = ''

    for i, node in enumerate(db_node_mappings):
        db_node_mappings[node] = couchbase.config_entry(cluster_name, i, uid,
                                                        docker_host)

    if not db_node_mappings:
        return db_node_mappings, {}

    [dns] = dns_servers
    couchbase_output = couchbase.up('couchbase/server:community-4.5.1', dns,
                                    uid, cluster_name, len(db_node_mappings),
                                    configurator.couchbase_buckets(),
                                    configurator.couchbase_ramsize(),
                                    docker_host)

    return db_node_mappings, couchbase_output


def _db_driver(config):
    return config['db_driver'] if 'db_driver' in config else 'couchdb'


def _db_docker_host(config):
    return config['db_docker_host'] if 'db_docker_host' in config else None


def _db_driver_module(db_driver):
    return db_driver + "_datastore_driver"


def up(image, bindir, dns_server, uid, config_path, configurator, logdir=None,
       storages_dockers=None):
    config = common.parse_json_config_file(config_path)

    input_dir = config['dirs_config'][configurator.app_name()]['input_dir']
    dns_servers, output = dns.maybe_start(dns_server, uid)

    # Workers of every cluster are started together
    # here we call that an instance
    for instance in config[configurator.domains_attribute()]:
        instance_config = config[configurator.domains_attribute()][instance]
        current_output = {}

        gen_dev_cfg = {
            'config': {
                'input_dir': input_dir,
                'target_dir': '/root/bin'
            },
            'nodes': instance_config[configurator.app_name()],
            'db_driver': _db_driver(instance_config)
        }

        # If present, include os_config
        if 'os_config' in instance_config:
            os_config = instance_config['os_config']
            gen_dev_cfg['os_config'] = config['os_configs'][os_config]

        # If present, include gui config
        if 'gui_override' in instance_config:
            gen_dev_cfg['gui_override'] = instance_config['gui_override']

        # Tweak configs, retrieve list of db nodes to start
        configs = []
        all_db_nodes = []

        db_driver = _db_driver(instance_config)
        db_docker_host = _db_docker_host(instance_config)

        for worker_node in gen_dev_cfg['nodes']:
            tw_cfg, db_nodes = _tweak_config(gen_dev_cfg, worker_node, instance,
                                             uid, configurator, db_docker_host)
            configs.append(tw_cfg)
            all_db_nodes.extend(db_nodes)

        db_node_mappings = None
        db_out = None

        # Start db nodes, obtain mappings
        if db_driver in ['couchbase', 'couchdb']:
            db_node_mappings, db_out = _couchbase_up(instance, all_db_nodes,
                                                     dns_servers, uid,
                                                     configurator,
                                                     db_docker_host)
        else:
            raise ValueError("Invalid db_driver: {0}".format(db_driver))

        common.merge(current_output, db_out)

        instance_domain = cluster_domain(instance, uid)

        # Call pre-start configuration for instance (cluster)
        configurator.pre_configure_instance(instance, instance_domain, config)

        # Start the workers
        workers = []
        worker_ips = []
        for cfg in configs:
            worker, node_out = _node_up(image, bindir, dns_servers, cfg,
                                        db_node_mappings, logdir, configurator,
                                        storages_dockers)
            workers.append(worker)
            worker_ips.append(common.get_docker_ip(worker))
            common.merge(current_output, node_out)

        # Wait for all workers to start

        common.wait_until(configurator.ready_check, workers,
                          CLUSTER_WAIT_FOR_NAGIOS_SECONDS)

        # Add the domain of current clusters, NS records if the cluster has
        # its own DNS server, A records if not
        domains = {
            'domains': {
                instance_domain: {
                    'ns': worker_ips if configurator.has_dns_server() else [],
                    'a': [] if configurator.has_dns_server() else worker_ips
                }
            },
            'domain_mappings': {
                instance: instance_domain
            }
        }
        common.merge(current_output, domains)
        common.merge(output, current_output)

        # Call post-start configuration for instance (cluster)
        configurator.post_configure_instance(bindir, instance, config,
                                             workers, current_output,
                                             storages_dockers)

    # Make sure domains are added to the dns server.
    dns.maybe_restart_with_configuration(dns_server, uid, output)
    return output
