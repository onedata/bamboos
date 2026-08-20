# coding=utf-8
"""Author: Konrad Zemek
Copyright (C) 2015 ACK CYFRONET AGH
This software is released under the MIT license cited in 'LICENSE.txt'

Functions wrapping capabilities of docker binary.

DEPRECATED: for new code, use docker_p3 instead, which is a Python 3 port.
"""

import json
import os
import subprocess
import sys
from six import string_types

PULL_DOCKER_IMAGE_RETRIES = 5


# Adds a bind-mount consistency option depending on the container's access_level.
# This option applies to macOS only, otherwise is ignored by Docker. It relaxes
# the consistency guarantees between the host and container:
#   * cached - the host is authoritative, writes on host may not be immediately
#              visible on the container. Improves performance of read-heavy
#              workloads.
#   * delegated - the container is authoritative, writes on the container may
#                 not be immediately visible on the host, but they will be
#                 flushed before the container exit. Improves performance of
#                 write-heavy workloads.
def with_consistency_opt(access_level):
    if access_level == 'ro':
        return 'ro,cached'
    elif access_level == 'rw':
        return 'rw,delegated'


# noinspection PyDefaultArgument
def run(image, docker_host=None, detach=False, dns_list=[], add_host={},
        envs={}, hostname=None, interactive=False, link={}, tty=False,
        rm=False, reflect=[], volumes=[], name=None, workdir=None, user=None,
        group=None, group_add=[], cpuset_cpus=None, privileged=False,
        publish=[], run_params=[], command=None, output=False, stdin=None,
        stdout=None, stderr=None, network=None):
    cmd = ['docker']

    cmd.append('run')

    if detach:
        cmd.append('-d')

    for addr in dns_list:
        cmd.extend(['--dns', addr])

    for key, value in list(add_host.items()):
        cmd.extend(['--add-host', '{0}:{1}'.format(key, value)])

    for key in envs:
        cmd.extend(['-e', '{0}={1}'.format(key, envs[key])])

    if hostname:
        cmd.extend(['-h', hostname])

    if network:
        cmd.extend(['--network', network])

    if detach or sys.__stdin__.isatty():
        if interactive:
            cmd.append('-i')
        if tty:
            cmd.append('-t')

    for container, alias in list(link.items()):
        cmd.extend(['--link', '{0}:{1}'.format(container, alias)])

    if name:
        cmd.extend(['--name', name])

    if rm:
        cmd.append('--rm')

    for path, access_level in reflect:
        vol = '{0}:{0}:{1}'.format(
            os.path.abspath(path), with_consistency_opt(access_level)
        )
        cmd.extend(['-v', vol])

    # Volume can be in one of three forms
    # 1. 'path_on_docker'
    # 2. ('path_on_host', 'path_on_docker', 'ro'/'rw')
    # 3. {'volumes_from': 'volume name'}
    for entry in volumes:
        if isinstance(entry, tuple):
            path, bind, access_level = entry
            vol = '{0}:{1}:{2}'.format(
                os.path.abspath(path), bind, with_consistency_opt(access_level)
            )
            cmd.extend(['-v', vol])
        elif isinstance(entry, dict):
            volume_name = entry['volumes_from']
            cmd.extend(['--volumes-from', volume_name])
        else:
            cmd.extend(['-v', entry])

    if workdir:
        cmd.extend(['-w', os.path.abspath(workdir)])

    if user:
        user_group = '{0}:{1}'.format(user, group) if group else user
        cmd.extend(['-u', user_group])

    for g in group_add:
        cmd.extend(['--group-add', g])

    if privileged:
        cmd.append('--privileged')

    for port in publish:
        if isinstance(port, tuple):
            cmd.extend(['-p', '{0}:{1}'.format(port[0], port[1])])
        else:
            cmd.extend(['-p', '{0}:{0}'.format(port)])

    if cpuset_cpus:
        cmd.extend(['--cpuset-cpus', cpuset_cpus])

    cmd.extend(run_params)
    cmd.append(image)

    cmd = format_command(cmd, command, docker_host)

    if detach or output:
        return subprocess.check_output(cmd, stdin=stdin, stderr=stderr).decode(
            'utf-8').strip()

    return subprocess.call(cmd, stdin=stdin, stderr=stderr, stdout=stdout)


def exec_(container, command, docker_host=None, user=None, group=None,
          detach=False, interactive=False, tty=False, privileged=False,
          output=False, stdin=None, stdout=None, stderr=None):
    cmd = ['docker']

    cmd.append('exec')

    if user:
        user_group = '{0}:{1}'.format(user, group) if group else user
        cmd.extend(['-u', user_group])

    if detach:
        cmd.append('-d')

    if detach or sys.__stdin__.isatty():
        if interactive:
            cmd.append('-i')
        if tty:
            cmd.append('-t')

    if privileged:
        cmd.append('--privileged')

    cmd.append(container)

    cmd = format_command(cmd, command, docker_host)

    if detach or output:
        return subprocess.check_output(cmd, stdin=stdin, stderr=stderr).decode(
            'utf-8').strip()

    return subprocess.call(cmd, stdin=stdin, stderr=stderr, stdout=stdout)


def inspect(container, docker_host=None, timeout=None, stderr=None):
    cmd = ['docker']

    cmd.extend(['inspect', container])

    if docker_host:
        cmd = wrap_in_ssh_call(cmd, docker_host)

    if timeout is not None:
        cmd = add_timeout_cmd(cmd, timeout)

    out = subprocess.check_output(cmd, universal_newlines=True, stderr=stderr)
    return json.loads(out)[0]


def logs(container, docker_host=None):
    cmd = ['docker']

    cmd.extend(['logs', container])

    if docker_host:
        cmd = wrap_in_ssh_call(cmd, docker_host)

    return subprocess.check_output(cmd, universal_newlines=True,
                                   stderr=subprocess.STDOUT)


def stop(containers, docker_host=None, stop_timeout=None, signal=None,
         command_timeout=None, stderr=None):
    cmd = ['docker', 'stop']

    if signal is not None:
        cmd.extend(['--signal', signal])

    if stop_timeout is not None:
        cmd.extend(['--timeout', str(stop_timeout)])

    if isinstance(containers, str):
        cmd.append(containers)
    else:
        cmd.extend(containers)

    if docker_host:
        cmd = wrap_in_ssh_call(cmd, docker_host)

    if command_timeout is not None:
        cmd = add_timeout_cmd(cmd, command_timeout)

    subprocess.check_call(cmd, stderr=stderr)


def remove(containers, docker_host=None, force=False,
           link=False, volumes=False, timeout=None, stderr=None):
    cmd = ['docker']

    cmd.append('rm')

    if force:
        cmd.append('-f')

    if link:
        cmd.append('-l')

    if volumes:
        cmd.append('-v')

    if isinstance(containers, str):
        cmd.append(containers)
    else:
        cmd.extend(containers)

    if docker_host:
        cmd = wrap_in_ssh_call(cmd, docker_host)

    if timeout is not None:
        cmd = add_timeout_cmd(cmd, timeout)

    subprocess.check_call(cmd, stderr=stderr)


def cp(container, src_path, dest_path, to_container=False, docker_host=None):
    """Copying file between docker container and host
    :param container: str, docker id or name
    :param src_path: str
    :param dest_path: str
    :param to_container: bool, if True file will be copied from host to
    container, otherwise from docker container to host
    :param docker_host: dict
    """
    cmd = ["docker", "cp"]
    if to_container:
        cmd.extend([src_path, "{0}:{1}".format(container, dest_path)])
    else:
        cmd.extend(["{0}:{1}".format(container, src_path), dest_path])

    if docker_host:
        cmd = wrap_in_ssh_call(cmd, docker_host)

    subprocess.check_call(cmd)


def login(user, password, repository='hub.docker.com'):
    """Logs into docker repository."""

    subprocess.check_call(['docker', 'login', '-u', user, '-p', password,
                           repository])


def build_image(image, build_args):
    """Builds and tags docker image."""

    subprocess.check_call(['docker', 'build', '--no-cache', '--force-rm', '-t',
                           image] + build_args)


def tag_image(image, tag):
    """Tags docker image."""

    subprocess.check_call(['docker', 'tag', image, tag])


def push_image(image):
    """Pushes docker image to the repository."""

    subprocess.check_call(['docker', 'push', image])


def pull_image(image):
    """Pulls docker image from the repository."""

    subprocess.check_call(['docker', 'pull', image])


def pull_image_with_retries(image, retries=PULL_DOCKER_IMAGE_RETRIES):
    attempts = 0

    while attempts < retries:
        try:
            pull_image(image)
        except subprocess.CalledProcessError as e:
            attempts += 1
            if attempts >= retries:
                print('Could not download image {}. Tried {} times. \n'
                      'Captured output from last call: {} \n'
                      .format(image, retries, e.output))
                raise
        else:
            return


def image_exists(image):
    """Checks whether docker image is in the repository."""

    with open(os.devnull, 'w') as DEVNULL:
        return 0 == subprocess.call(
            ['docker', 'manifest', 'inspect', image],
            stdout=DEVNULL,
            stderr=DEVNULL
        )


def remove_image(image):
    """Removes docker image."""

    subprocess.check_call(['docker', 'rmi', '-f', image])


def create_volume(path, name, image, command):
    cmd = ['docker']

    cmd.append('create')
    cmd.append('-v')
    cmd.append(path)

    cmd.append('--name')
    cmd.append(name)

    cmd.append(image)

    cmd.append(command)

    return subprocess.check_output(cmd, universal_newlines=True,
                                   stderr=subprocess.STDOUT)


def ps(all=False, quiet=False, filters=None):
    """
    List containers
    """
    cmd = ["docker", "ps"]
    if all:
        cmd.append("--all")
    if quiet:
        cmd.append("--quiet")
    if filters:
        for f in filters:
            cmd.extend(['-f', '{}={}'.format(f[0], f[1])])

    return subprocess.check_output(cmd, universal_newlines=True).split()


def list_volumes(quiet=True):
    """
    List volumes
    """
    cmd = ["docker", "volume", "ls"]
    if quiet:
        cmd.append("--quiet")
    return subprocess.check_output(cmd,  universal_newlines=True).split()


def remove_volumes(volumes, timeout=None, stderr=None):
    """
    Remove volumes
    """
    cmd = ["docker", "volume", "rm"]
    if isinstance(volumes, str):
        cmd.append(volumes)
    else:
        cmd.extend(volumes)

    if timeout is not None:
        cmd = add_timeout_cmd(cmd, timeout)

    return subprocess.check_call(cmd, stderr=stderr)


def connect_docker_to_network(network, container):
    """
    Connect docker to the network
    Useful when dockers are in different subnetworks and they need to see each other using IP address
    """

    subprocess.check_call(['docker', 'network', 'connect', network, container])


def format_command(docker_cmd, entry_point, docker_host):
    if isinstance(entry_point, string_types) and docker_host is not None:
        docker_cmd.extend(['sh', '-c', '\"' + entry_point + '\"'])
    elif isinstance(entry_point, string_types):
        docker_cmd.extend(['sh', '-c', entry_point])
    elif isinstance(entry_point, list):
        docker_cmd.extend(entry_point)
    elif entry_point is not None:
        raise ValueError('{0} is not a string nor list'.format(entry_point))

    if docker_host:
        docker_cmd = wrap_in_ssh_call(docker_cmd, docker_host)

    return docker_cmd


def wrap_in_ssh_call(docker_cmd, docker_host):
    username = docker_host['ssh_username']
    hostname = docker_host['ssh_hostname']
    port = docker_host['ssh_port'] if 'ssh_port' in docker_host else 22
    return ['ssh', '-p', port, '{0}@{1}'.format(username, hostname), ' '.join(docker_cmd)]


def add_timeout_cmd(cmd, timeout):
    timeout_cmd = ['timeout', '--kill-after', str(timeout), str(timeout)]
    return timeout_cmd + cmd
