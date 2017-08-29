#!/usr/bin/env python
# coding=utf-8

"""Author: Michał Ćwiertnia
Copyright (C) 2016-2017 ACK CYFRONET AGH
This software is released under the MIT license cited in 'LICENSE.txt'

This file is mainly used in onedata tests.

Starts scenario 2.0 or 2.1 from onedata's getting started.
Runs isolated Onedata deployment consisting of:
- a single node preconfigured Onezone instance
- a single node preconfigured Oneprovider instance

To run this script manually:
- run script from onedata repo root dir
- make sure there is tests/gui directory in onedata repo root dir
- make sure you have python libraries: urllib3, certifi
- make sure you have getting_started, onezone_swagger and onepanel_swagger submodules
- build swagger clients running command: "make build_swaggers" from onedata repo root dir

Run the script with -h flag to learn about script's running options.
"""

import sys
sys.path.append('.')

from environment import docker
from subprocess import Popen, PIPE, STDOUT
import os
import re
import time
import json
import argparse


SCENARIOS_DIR_PATH = os.path.join('getting_started', 'scenarios')
TIMEOUT = 60 * 10


def print_logs(service_name, service_docker_logs):
    print '{} docker logs:'.format(service_name)
    print service_docker_logs

    path = os.path.join(scenario_path, 'config_' + service_name, 'var', 'log')
    try:
        directories = os.listdir(path)
    except IOError:
        print 'Couldn\'t find {}'.format(path)
    else:
        for directory in directories:
            try:
                files = os.listdir(os.path.join(path, directory))
            except IOError:
                print 'Couldn\'t find {}'.format(os.path.join(path, directory))
            else:
                for file in files:
                    try:
                        with open(os.path.join(path, directory, file), 'r') \
                                as logs:
                            print '{service_name} {dir} {file}'.format(
                                                    service_name=service_name,
                                                    dir=directory,
                                                    file=file)

                            print logs.readlines()
                    except IOError:
                        print 'Couldn\'t find {}'.format(
                            os.path.join(path, directory, file))


PERSISTENCE = ('# configuration persistance',
               '# data persistance',
               '# configuration persistence',
               '# data persistence')


def rm_persistence(path, service_name):
    """Remove persistence of configuration/data.
    """
    service_path = os.path.join(path, 'docker-compose-{}.yml'
                                      ''.format(service_name))
    with open(service_path, 'r+') as f:
        lines = f.readlines()

        comment = False
        for i, line in enumerate(lines):
            if comment:
                lines[i] = '#{}'.format(line) if line[0] != '#' else line
                comment = False
            if any(per in line for per in PERSISTENCE):
                comment = True

        f.seek(0)
        f.writelines(lines)


def get_service_url(docker_name, service_ip):
    service_process = Popen(['docker', 'inspect',
                             '--format=\'{{json .Config}}\'', docker_name],
                            stdout=PIPE, stderr=STDOUT)
    docker_conf = service_process.communicate()[0]
    hostname = re.search(r'"Hostname":"(?P<hostname>.*?)"',
                         docker_conf, re.I).group('hostname')
    domain = re.search(r'"Domainname":"(?P<domain>.*?)\."',
                       docker_conf, re.I).group('domain')
    url = '{}.{}'.format(hostname, domain)

    with open('/etc/hosts', 'a') as f:
        f.write('\n{} {}\n'.format(service_ip, url))

    return url


def get_service_ip(docker_name, service_name, timeout):
    timeout = time.time() + timeout
    service_ip = None
    re_docker_ip = re.compile(r'IP Address:\s*(?P<ip>(\d{1,3}\.?){4})')
    while not service_ip:
        service_process = Popen(['docker', 'logs', docker_name], stdout=PIPE,
                                stderr=STDOUT)
        docker_logs = service_process.communicate()[0]
        service_ip = re_docker_ip.search(docker_logs)
        if re.search('Error', docker_logs):
            print 'Error while starting {}'.format(service_name)
            print_logs(service_name, docker_logs)
            exit(1)
        if time.time() > timeout:
            print ('Timeout while waiting for {}\'s IP '
                   'address'.format(service_name))
            print_logs(service_name, docker_logs)
            exit(1)
        time.sleep(2)
    service_ip = service_ip.group('ip')
    print '{service_name} IP: {service_ip}'.format(service_name=service_name,
                                                   service_ip=service_ip)
    return service_ip


def start_service(start_service_path, start_service_args, service_name,
                  timeout):
    """
    service_name argument is one of: onezone, oneprovider
    Runs ./run_onedata.sh script from given onedata's getting started scenario
    Returns ip of started service
    """
    service_process = Popen(['./run_onedata.sh'] + start_service_args,
                            stdout=PIPE, stderr=STDOUT, cwd=start_service_path)
    service_output = service_process.communicate()[0]
    print service_output
    service = 'onezone' if service_name == 'oz_panel' else 'oneprovider'
    docker_name = re.search(r'Creating\s*(?P<name>{}[\w-]+)\b'.format(service),
                            service_output).group('name')

    service_ip = get_service_ip(docker_name, service_name, timeout)
    url = get_service_url(docker_name, service_ip)
    return url


parser = argparse.ArgumentParser()
parser.add_argument('--docker-name',
                    action='store',
                    default='',
                    help='Name of docker that will be added to network',
                    required=False)
parser.add_argument('--scenario',
                    action='store',
                    default='2_0_oneprovider_onezone',
                    help='Getting started scenario\'s name',
                    required=False)
parser.add_argument('--zone_name',
                    action='store',
                    default='z1',
                    help='Zone\'s name',
                    required=False)
parser.add_argument('--provider_name',
                    action='store',
                    default='p1',
                    help='Provider\'s name',
                    required=False)
args = parser.parse_args()


start_onezone_args = ['--zone', '--detach', '--with-clean', '--name',
                      args.zone_name]
start_oneprovider_args = ['--provider', '--detach', '--without-clean', '--name',
                          args.provider_name]

scenario_path = os.path.join(SCENARIOS_DIR_PATH, args.scenario)
scenario_network = '{}_{}'.format(args.scenario.replace('_', ''), 'scenario2')
print 'Starting onezone'
rm_persistence(scenario_path, 'onezone')
oz_panel_url = start_service(scenario_path, start_onezone_args, 'oz_panel',
                             TIMEOUT)
print 'Starting oneprovider'
rm_persistence(scenario_path, 'oneprovider')
op_panel_url = start_service(scenario_path, start_oneprovider_args, 'op_panel',
                             TIMEOUT)

if args.docker_name:
    docker.connect_docker_to_network(scenario_network, args.docker_name)

output = {
    'oneprovider_host': op_panel_url,
    'onezone_host': oz_panel_url,
    'op_panel_host': op_panel_url,
    'oz_panel_host': oz_panel_url
}

print json.dumps(output)
