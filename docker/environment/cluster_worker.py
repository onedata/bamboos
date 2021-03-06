"""Author: Michal Zmuda
Copyright (C) 2015 ACK CYFRONET AGH
This software is released under the MIT license cited in 'LICENSE.txt'

Brings up a set of cluster-worker nodes. They can create separate clusters.
"""

from . import worker, docker, common

def up(image, bindir, dns_server, uid, config_path, logdir=None,
       storages_dockers=None):
    return worker.up(image, bindir, dns_server, uid, config_path,
                     ClusterWorkerConfigurator(), logdir,
                     storages_dockers=storages_dockers)


class ClusterWorkerConfigurator:
    def tweak_config(self, cfg, uid, instance):
        return cfg

    def pre_start_commands(self, domain):
        return 'escript bamboos/gen_dev/gen_dev.escript /tmp/gen_dev_args.json'

    # Called BEFORE the instance (cluster of workers) is started,
    # once for every instance
    def pre_configure_instance(self, instance, instance_domain, config):
        pass

    # Called AFTER the instance (cluster of workers) has been started
    def post_configure_instance(self, bindir, instance, config, container_ids,
                                output, storages_dockers=None):
        pass

    def extra_volumes(self, config, bindir, instance_domain, storages_dockers):
        return []

    def couchbase_ramsize(self):
        return 1024

    def couchbase_buckets(self):
        return {"onedata": 512}

    def app_name(self):
        return "cluster_worker"

    def domains_attribute(self):
        return "cluster_domains"

    def domain_env_name(self):
        return "cluster_domain"

    def nodes_list_attribute(self):
        return "cluster_worker_nodes"

    def has_dns_server(self):
        return False

    def ready_check(self, container):
        ip = docker.inspect(container)['NetworkSettings']['IPAddress']
        return common.nagios_up(ip, '80', 'http')
