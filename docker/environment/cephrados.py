# coding=utf-8
"""Author: Bartek Kryza
Copyright (C) 2018 ACK CYFRONET AGH
This software is released under the MIT license cited in 'LICENSE.txt'

Brings up a Ceph storage cluster.
"""

import re
import sys
from .timeouts import *

from . import common, docker


def _ceph_ready(container):
    output = docker.exec_(container, ['ceph', 'health'], output=True,
                          stdout=sys.stderr)
    return bool(re.search('HEALTH_OK', output))


def _node_up(image, pools, name, uid):
    hostname = common.format_hostname([name, 'cephrados'], uid)
    
    container = docker.run(
            image=image,
            hostname=hostname,
            name=hostname,
            privileged=True,
            detach=True)

    for (name, pg_num) in pools:
        docker.exec_(container, ['ceph', 'osd', 'pool', 'create', name, pg_num])

    common.wait_until(_ceph_ready, [container], CEPH_READY_WAIT_SECONDS)

    username = 'client.admin'
    key = docker.exec_(container, ['ceph', 'auth', 'print-key', username],
                       output=True)
    settings = docker.inspect(container)
    ip = settings['NetworkSettings']['IPAddress']

    return {
        'docker_ids': [container],
        'username': username,
        'key': key,
        'host_name': ip,
        'container_id': container
    }


def up(image, pools, name, uid):
    return _node_up(image, pools, name, uid)
