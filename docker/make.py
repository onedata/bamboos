#!/usr/bin/env python3

# coding=utf-8
"""Author: Konrad Zemek
Copyright (C) 2015 ACK CYFRONET AGH
This software is released under the MIT license cited in 'LICENSE.txt'

Runs a command in a dockerized development environment. The files are copied
from 'source directory' to 'output directory' and then the command is ran.
The copy operation is optimized, so that only new and changed files are copied.
The script uses user's SSH keys in case dependency fetching is needed.

Unknown arguments will be passed to the command.

Run the script with -h flag to learn about script's running options.
"""

from os.path import expanduser
import argparse
import os
import platform
import sys
import socket
import re

from environment import docker, dockers_config


def default_keys_location():
    ssh_dir = expanduser('~/.ssh')
    ssh_slash_docker = os.path.join(ssh_dir, 'docker')
    if os.path.isdir(ssh_slash_docker):
        ssh_dir = ssh_slash_docker
    return ssh_dir


# Useful on macOS where the /var directory is a link to /private/var
def autodetect_cache_dir():
    var_dir = "/var"
    try:
        link = os.readlink(var_dir)
        var_dir = os.path.join("/", link)
    except OSError:
        pass
    return os.path.join(var_dir, "cache")


parser = argparse.ArgumentParser(
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    description='Run a command inside a dockerized development environment.')

parser.add_argument(
    '-i', '--image',
    action='store',
    default=None,
    help='override of docker image for building',
    dest='image')

parser.add_argument(
    '-s', '--src',
    action='store',
    default=os.getcwd(),
    help='source directory to run make from',
    dest='src')

parser.add_argument(
    '--no-cache',
    action='store_false',
    default=True,
    help='disable mounting /var/cache/ccache and /var/cache/rebar3',
    dest='mount_cache')

parser.add_argument(
    '--cache-prefix',
    action='store',
    default=autodetect_cache_dir(),
    help='Specify the cache prefix on host system (default: /var/cache)',
    dest='cache_prefix')

parser.add_argument(
    '-k', '--keys',
    action='store',
    default=default_keys_location(),
    help='directory of ssh keys used for dependency fetching',
    dest='keys')

parser.add_argument(
    '-r', '--reflect-volume',
    action='append',
    default=[],
    help="host's paths to reflect in container's filesystem",
    dest='reflect')

parser.add_argument(
    '-c', '--command',
    action='store',
    default='make',
    help='command to run in the container',
    dest='command')

parser.add_argument(
    '-w', '--workdir',
    action='store',
    default=None,
    help='path to the working directory; defaults to src dir if unset',
    dest='workdir')

parser.add_argument(
    '-e', '--env',
    action='append',
    default=[],
    help='env variables to set in the environment',
    dest='envs')

parser.add_argument(
    '--group',
    action='append',
    default=[],
    help='system groups user should be a part of',
    dest='groups')

parser.add_argument(
    '--privileged',
    action='store_true',
    default=False,
    help='run the container with --privileged=true',
    dest='privileged')

parser.add_argument(
    '--grant-sudo-rights',
    action='store_true',
    default=False,
    help='grant sudo rights for the user maketmp created eventually',
    dest='grant_sudo_rights')

parser.add_argument(
    '--cpuset-cpus',
    action='store',
    default=None,
    help='CPUs in which to allow execution (0-3, 0,1)',
    dest='cpuset_cpus')

parser.add_argument(
    '--add-git-host',
    action='store',
    default='10.87.23.110',
    help='IP address for git.onedata.org host mapping',
    dest='add_git_host')

[args, pass_args] = parser.parse_known_args()
dockers_config.ensure_image(args, 'image', 'builder')

# Handle git host IP configuration with proper precedence
# Priority: CLI argument > environment variable > default
git_host_ip = args.add_git_host  # starts with default from argparse
if 'bamboo.gitOnedataOrgIP' in os.environ and not any('--add-git-host' in arg for arg in sys.argv):
    git_host_ip = os.environ['bamboo.gitOnedataOrgIP']

# Check if make.py is run on a bamboo agent
# If the script is run on a bamboo agent git-cache-http-server will be used.
# As proxy.devel.onedata.org resolves to a private address in the onedata-devel tenant
# it should not be used when building outside of a bamboo agent.
# Call git config modification from user's home (note the 'cd' command), as calling it from
# within a repo (especially a submodule) may fail, despite the fact that --global is used.
if re.match('bamboo-agent-.*', socket.gethostname()):
    git_config_sh = """    
    cd 
    git config --global --replace-all url.http://proxy.devel.onedata.org:8080/github.com/.insteadOf git://github.com/
    git config --global --add url.http://proxy.devel.onedata.org:8080/github.com/.insteadOf https://github.com/
    """
else:
    git_config_sh = """    
    cd 
    git config --global url.https://github.com/.insteadOf git://github.com/
    """

command = '''
import os, shutil, subprocess, sys

os.environ['HOME'] = '/root'

ssh_home = '/root/.ssh'
docker_home = '/root/.docker/'
if {shed_privileges}:
    useradd = ['useradd', '--create-home', '--uid', '{uid}', 'maketmp']
    if {groups}:
        useradd.extend(['-G', ','.join({groups})])

    subprocess.call(useradd)
    if {grant_sudo_rights}:
        subprocess.call(['bash', '-c', 'if grep focal /etc/os-release; then echo "maketmp ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/S51-maketmp; fi'])

    os.environ['PATH'] = os.environ['PATH'].replace('sbin', 'bin')
    os.environ['HOME'] = '/home/maketmp'
    ssh_home = '/home/maketmp/.ssh'
    docker_home = '/home/maketmp/.docker'
    docker_gid = os.stat('/var/run/docker.sock').st_gid
    os.setgroups([docker_gid])
    os.setregid({gid}, {gid})
    os.setreuid({uid}, {uid})

shutil.copytree('/tmp/keys', ssh_home)
for root, dirs, files in os.walk(ssh_home):
    for dir in dirs:
        os.chmod(os.path.join(root, dir), 0o700)
    for file in files:
        os.chmod(os.path.join(root, file), 0o600)

# Try to copy config.json, continue if it fails (might not exist on host).
try:
    os.makedirs(docker_home)
except:
    pass
try:
    shutil.copyfile(
        '/tmp/docker_config/config.json',
        os.path.join(docker_home, 'config.json'
    ))
except:
    pass

subprocess.call([
    'sh', '-c', \'\'\'''' + git_config_sh + '''\'\'\'
])

sh_command = (
    'eval $(ssh-agent) > /dev/null; '
    'ssh-add 2>&1; '
    '{command} {params}'
)
ret = subprocess.call(['sh', '-c', sh_command])
sys.exit(ret)
'''

command = command.format(
    command=args.command,
    params=' '.join(pass_args),
    uid=os.geteuid(),
    gid=os.getegid(),
    src=args.src,
    shed_privileges=(platform.system() == 'Linux' and os.geteuid() != 0),
    grant_sudo_rights=args.grant_sudo_rights,
    groups=args.groups)

# Mount docker socket so dockers can start dockers
reflect = [(args.src, 'rw'), ('/var/run/docker.sock', 'rw')]
reflect.extend(list(zip(args.reflect, ['rw'] * len(args.reflect))))

# Mount keys required for git and docker config that holds auth to
# docker.onedata.org, so the docker can pull images from there.
# Mount it in /tmp/docker_config and then cp the json.
# If .docker is not existent on host, just skip the volume and config copying.
volumes = [
    (args.keys, '/tmp/keys', 'ro')
]

if args.mount_cache:
    volumes.extend([
        ("%s/ccache"%(args.cache_prefix), '/var/cache/ccache', 'rw'),
        ("%s/rebar3"%(args.cache_prefix), '/var/cache/rebar3', 'rw')
    ])

if os.path.isdir(expanduser('~/.docker')):
    volumes += [(expanduser('~/.docker'), '/tmp/docker_config', 'ro')]

split_envs = [e.split('=') for e in args.envs]
envs = {kv[0]: kv[1] for kv in split_envs}

ret = docker.run(tty=True,
                 interactive=True,
                 rm=True,
                 reflect=reflect,
                 volumes=volumes,
                 envs=envs,
                 workdir=args.workdir if args.workdir else args.src,
                 image=args.image,
                 privileged=args.privileged,
                 cpuset_cpus=args.cpuset_cpus,
                 add_host={"git.onedata.org": git_host_ip},
                 command=['python3', '-c', command])
sys.exit(ret)
