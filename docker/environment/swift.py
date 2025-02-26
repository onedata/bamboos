# coding=utf-8
"""Author: Michal Wrona
Copyright (C) 2016 ACK CYFRONET AGH
This software is released under the MIT license cited in 'LICENSE.txt'

Brings up a Swift storage with Keystone auth.
"""

import sys
import time
import subprocess

from .timeouts import *
from . import common, docker

SWIFT_COMMAND = \
    'swift --os-auth-url http://{0}:5000/v3 \
      --os-project-name swift-project \
      --os-username swift \
      --os-password veryfast \
      --os-user-domain-name Default \
      --os-project-domain-name Default \
      --os-identity-api-version 3 \
      {1}'


def _get_swift_ready(ip):
    def _swift_ready(container):
        try:
            cmd = SWIFT_COMMAND.format(ip, 'stat')
            output = docker.exec_(container, [
                'bash', '-c', cmd], output=True, stdout=sys.stderr)
        except subprocess.CalledProcessError:
            return False
        else:
            return 'Account:' in output

    return _swift_ready


def _node_up(image, containers, name, uid):
    hostname = common.format_hostname([name, 'swift'], uid)

    container = docker.run(
        image=image,
        hostname=hostname,
        name=hostname,
        privileged=False,
        detach=True,
        tty=True,
        interactive=True,
        envs={'S6_LOGGING': '0'},
        run_params=[])

    settings = docker.inspect(container)
    ip = settings['NetworkSettings']['IPAddress']

    common.wait_until(_get_swift_ready(ip), [container],
                      SWIFT_READY_WAIT_SECONDS)
    # Sometimes swift returns internal server error few times
    # after first successful request
    time.sleep(2)
    common.wait_until(_get_swift_ready(ip), [container],
                      SWIFT_READY_WAIT_SECONDS)

    for c in containers:
        cmd = SWIFT_COMMAND.format(ip, 'post ' + c).split()
        docker.exec_(container, cmd, output=True, stdout=sys.stderr)

    return {
        'docker_ids': [container],
        'user_name': 'swift',
        'password': 'veryfast',
        'project_name': 'swift-project',
        'user_domain_name': 'Default',
        'project_domain_name': 'Default',
        'host_name': ip,
        'keystone_port': 5000,
        'swift_port': 8080,
        'keystone_admin_port': 35357,
        'swift_browser_port': 8000,
        'horizon_dashboard_port': 8081,
    }


def up(image, containers, name, uid):
    return _node_up(image, containers, name, uid)
