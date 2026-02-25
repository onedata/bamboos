#!/usr/bin/env python3

"""Author: Konrad Zemek
Copyright (C) 2015 ACK CYFRONET AGH
This software is released under the MIT license cited in 'LICENSE.txt'

Runs oneprovider integration tests, providing Erlang's ct_run with every
environmental argument it needs for successful run. The output is put into
'test_distributed/logs'. The (init|end)_per_suite "testcases" are removed from
the surefire.xml output.

All paths used are relative to script's path, not to the running user's CWD.
Run the script with -h flag to learn about script's running options.
"""



from os.path import expanduser
import argparse
import json
import os
import platform
import re
import shutil
import sys
import time
import glob
import fnmatch
import xml.etree.ElementTree as ElementTree

sys.path.insert(0, 'bamboos/docker')
from environment import docker, dockers_config
from environment.common import HOST_STORAGE_PATH, remove_dockers_and_volumes


def skipped_test_exists(junit_report_path):
    reports = glob.glob(junit_report_path)
    # if there are many reports, check only the last one
    reports.sort()
    tree = ElementTree.parse(reports[-1])
    testsuites = tree.getroot()
    for testsuite in testsuites:
        if testsuite.attrib['skipped'] != '0':
            return True
    return False


def locate_suite(name):
# TODO: https://jira.onedata.org/browse/VFS-9025
    if '/' in name:
        print(
            'NOTE: it is no longer required to provide full path(s) to the suite(s) you wish to run. '
            'It is enough to provide the suite name (without the "_test_SUITE" suffix).'
        )
        name = os.path.basename(name)
    if '_test_SUITE' not in name:
        name += '_test_SUITE'
    if '.erl' not in name:
        name += '.erl'
    return find_suite_file(name)


def find_suite_file(name):
    for root, dirs, files in os.walk('test_distributed'):
        if name in files:
            return os.path.relpath(os.path.join(root, name), 'test_distributed')
    print('ERROR: Suite with name {} has not been found in the test_distributed directory'.format(name))
    sys.exit(1)


parser = argparse.ArgumentParser(
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    description='Run Common Tests.')

parser.add_argument(
    '--image', '-i',
    action='store',
    default=None,
    help='override of docker image to use as test master.',
    dest='image')

parser.add_argument(
    '--suite', '-s',
    action='append',
    help='name of the test suite',
    dest='suites')

parser.add_argument(
    '--group', '-g',
    action='append',
    help='name of the test group (can be repeated)',
    dest='groups')

parser.add_argument(
    '--case', '-c',
    action='append',
    help='name of the test case (can be repeated)',
    dest='cases')

parser.add_argument(
    '--performance', '-p',
    action='store_true',
    default=False,
    help='run performance tests',
    dest='performance')

parser.add_argument(
    '--cover',
    action='store_true',
    default=False,
    help='run cover analysis',
    dest='cover')

parser.add_argument(
    '--stress',
    action='store_true',
    default=False,
    help='run stress tests',
    dest='stress')

parser.add_argument(
    '--stress-no-clearing',
    action='store_true',
    default=False,
    help='run stress tests without clearing data between test cases',
    dest='stress_no_clearing')

parser.add_argument(
    '--stress-time',
    action='store',
    help='time of stress test in sek',
    dest='stress_time')

parser.add_argument(
    '--auto-compile',
    action='store_true',
    default=False,
    help='compile test suites before run',
    dest='auto_compile')

parser.add_argument(
    '--no-clean',
    action='store_true',
    help='if set, environment will not be cleaned up after tests',
    dest='no_clean')

args = parser.parse_args()
dockers_config.ensure_image(args, 'image', 'worker')

script_dir = os.path.dirname(os.path.abspath(__file__))
uid = str(int(time.time()))

if 'bamboo_coverOptionOverride' in os.environ:
    print("----------------------------------------------------")
    if os.environ['bamboo_coverOptionOverride'] == "true":
        print("NOTE: overriding cover option to 'true' according to ${bamboo_coverOptionOverride} ENV variable")
        args.cover = True
    elif os.environ['bamboo_coverOptionOverride'] == "false":
        print("NOTE: overriding cover option to 'false' according to ${bamboo_coverOptionOverride} ENV variable")
        args.cover = False
    elif os.environ['bamboo_coverOptionOverride'] == "develop_only":
        if 'bamboo_planRepository_branchName' in os.environ and \
            os.environ['bamboo_planRepository_branchName'] == "develop":

            print(
                "NOTE: overriding cover option to 'true' for branch 'develop' "
                "according to ${bamboo_coverOptionOverride} ENV variable"
            )
            args.cover = True
        else:
            print(
                "NOTE: overriding cover option to 'false' for branch other than 'develop' "
                "according to ${bamboo_coverOptionOverride} ENV variable"
            )
            args.cover = False
    else:
        print("WARNING: ignoring bad value for ${{bamboo_coverOptionOverride}} ENV variable - '{}'".format(
            os.environ['bamboo_coverOptionOverride']
        ))
    print("----------------------------------------------------")
    sys.stdout.flush()

excl_mods = glob.glob(
    os.path.join(script_dir, 'test_distributed', '*.erl'))
excl_mods = [os.path.basename(item)[:-4] for item in excl_mods]

cover_template = os.path.join(script_dir, 'test_distributed', 'cover.spec')
new_cover = os.path.join(script_dir, 'test_distributed', 'cover_tmp.spec')

incl_dirs = []
with open(cover_template, 'r') as template, open(new_cover, 'w') as cover:
    for line in template:
        if 'incl_dirs_r' in line:
            dirs_string = re.search(r'\[(.*?)\]', line).group(1)
            incl_dirs = [os.path.join(script_dir, d[1:]) for d in
                         dirs_string.split(', ')]
            docker_dirs = [os.path.join(script_dir, d[1:-1]) for d in
                           dirs_string.split(', ')]
        elif 'excl_mods' in line:
            modules_string = re.search(r'\[(.*?)\]', line).group(1)
            excl_mods.extend([d.strip('"') for d in modules_string.split(', ')])
        else:
            print(line, file=cover)

    print('{{incl_dirs_r, ["{0}]}}.'.format(', "'.join(incl_dirs)), file=cover)
    print('{{excl_mods, [{0}]}}.'.format(
        ', '.join(excl_mods)), file=cover)

ct_command = ['ct_run',
              '-abort_if_missing_suites',
              '-dir', '.',
              '-logdir', './logs/',
              '-ct_hooks', 'cth_surefire', '[{path, "surefire.xml"}]',
              'and', 'cth_logger', 'and', 'cth_env_up', 'and', 'cth_mock',
              'and', 'cth_posthook',
              '-noshell',
              '-name', 'testmaster@testmaster.{0}.test'.format(uid),
              '-include', './include', '../include', '../_build/default/lib']

code_paths = ['-pa']
if incl_dirs:
    code_paths.extend([os.path.join(script_dir, item[:-1])
                       for item in incl_dirs])
code_paths.extend(
    glob.glob(os.path.join(script_dir, '_build/default/lib', '*', 'ebin')))
ct_command.extend(code_paths)

if args.suites:
    ct_command.append('-suite')
    ct_command.extend([locate_suite(s) for s in args.suites])

if args.cases:
    ct_command.append('-case')
    ct_command.extend(args.cases)

if args.groups:
    ct_command.append('-group')
    ct_command.extend(args.groups)

if args.stress_time:
    ct_command.extend(['-env', 'stress_time', args.stress_time])

ct_command.extend(['-env', 'clean_env', "false" if args.no_clean else "true"])

if args.performance:
    ct_command.extend(['-env', 'performance', 'true'])
elif args.stress:
    ct_command.extend(['-env', 'stress', 'true'])
elif args.stress_no_clearing:
    ct_command.extend(['-env', 'stress_no_clearing', 'true'])
elif args.cover:
    print("----------------------------------------------------")
    print("Cover is enabled, the tests will take longer to run due to setup and later analysis.")
    print("----------------------------------------------------")
    sys.stdout.flush()
    ct_command.extend(['-cover', 'cover_tmp.spec'])

    env_descs = []
    tests_dir = os.path.join(script_dir, 'test_distributed')
    for root, dirnames, filenames in os.walk(tests_dir):
        for filename in fnmatch.filter(filenames, 'env_desc.json'):
            env_descs.append(os.path.join(root, filename))

    for file in env_descs:
        shutil.copyfile(file, file + '.bak')
        with open(file, 'r') as jsonFile:
            data = json.load(jsonFile)

            configs_to_change = []
            repo_name = os.popen("basename -s .git `git config --get remote.origin.url`").read().strip()

            if repo_name == "onepanel" and 'onepanel_domains' in data:
                for onepanel in data['onepanel_domains']:
                    configs_to_change.append(
                        ('onepanel', list(data['onepanel_domains'][onepanel][
                            'onepanel'].values()))
                    )
            elif repo_name == "op-worker" and 'provider_domains' in data:
                for provider in data['provider_domains']:
                    if 'op_worker' in data['provider_domains'][provider]:
                        configs_to_change.append(
                            ('op_worker', list(data['provider_domains'][provider][
                                'op_worker'].values()))
                        )
                    if 'cluster_manager' in data['provider_domains'][provider]:
                        configs_to_change.append(
                            ('cluster_manager',
                             list(data['provider_domains'][provider][
                                 'cluster_manager'].values()))
                        )
            elif repo_name == "oz-worker" and 'zone_domains' in data:
                for zone in data['zone_domains']:
                    configs_to_change.append(
                        ('oz_worker',
                         list(data['zone_domains'][zone]['oz_worker'].values()))
                    )
                    configs_to_change.append(
                        ('oz_worker',
                         list(data['zone_domains'][zone]['cluster_manager'].values()))
                    )
            elif repo_name == "cluster-manager" and 'cluster_domains' in data:
                for cluster in data['cluster_domains']:
                    if 'cluster_worker' in data['cluster_domains'][cluster]:
                        configs_to_change.append(
                            ('cluster_worker', list(data['cluster_domains'][cluster][
                                'cluster_worker'].values()))
                        )
                    if 'cluster_manager' in data['cluster_domains'][cluster]:
                        configs_to_change.append(
                            ('cluster_manager',
                             list(data['cluster_domains'][cluster][
                                 'cluster_manager'].values()))
                        )

            for (app_name, configs) in configs_to_change:
                for config in configs:
                    if app_name in config['sys.config']:
                        config['sys.config'][app_name][
                            'covered_dirs'] = docker_dirs
                        config['sys.config'][app_name][
                            'covered_excluded_modules'] = excl_mods
                    elif 'cluster_manager' in config['sys.config']:
                        config['sys.config']['cluster_manager'][
                            'covered_dirs'] = docker_dirs
                        config['sys.config']['cluster_manager'][
                            'covered_excluded_modules'] = excl_mods
                    else:
                        config['sys.config']['covered_dirs'] = docker_dirs
                        config['sys.config'][
                            'covered_excluded_modules'] = excl_mods

            with open(file, 'w') as jsonFile:
                jsonFile.write(json.dumps(data))

# path to custom test node config adjusting logger behaviour
config_path = os.path.abspath("bamboos/env_configurator/test.config")
ct_command.extend(["-erl_args", "-enable-feature", "maybe_expr", "-config", config_path])

command = '''
import os, shutil, subprocess, sys, stat

os.environ['HOME'] = '/root'

docker_home = '/root/.docker/'
if {shed_privileges}:
    useradd = ['useradd', '--create-home', '--uid', '{uid}', 'maketmp']

    subprocess.call(useradd)

    os.environ['PATH'] = os.environ['PATH'].replace('sbin', 'bin')
    os.environ['HOME'] = '/home/maketmp'
    docker_home = '/home/maketmp/.docker'
    docker_gid = os.stat('/var/run/docker.sock').st_gid
    os.chmod('/etc/resolv.conf', 0o666)
    os.setgroups([docker_gid])
    os.setregid({gid}, {gid})
    os.setreuid({uid}, {uid})

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

command = {cmd}
ret = subprocess.call(command)

import xml.etree.ElementTree as ElementTree, glob, re
for file in glob.glob('logs/*/surefire.xml'):
    tree = ElementTree.parse(file)
    for suite in tree.findall('.//testsuite'):
        for test in suite.findall('testcase'):
            match = re.match('(init|end)_per_suite', test.attrib['name'])
            if match is not None:
                suite.remove(test)
    tree.write(file)

sys.exit(ret)
'''
command = command.format(
    uid=os.geteuid(),
    gid=os.getegid(),
    cmd=ct_command,
    shed_privileges=(platform.system() == 'Linux'))

volumes = []

# The /tmp/onedata directory is required for the no_clean option to work
# (test_node_starter stores the previous env there)
if args.no_clean:
    os.makedirs('/tmp/onedata', exist_ok=True)
    stat_info = os.stat('/tmp/onedata')
    if stat_info.st_uid != os. geteuid() or stat_info.st_gid != os. getegid():
        print('Directory /tmp/onedata does not belong to the current user. Delete it and run again.')
        sys.exit(1)
    volumes += [('/tmp/onedata', '/tmp/onedata', 'rw')]

if os.path.isdir(expanduser('~/.docker')):
    volumes += [(expanduser('~/.docker'), '/tmp/docker_config', 'ro')]

remove_dockers_and_volumes()

ret = docker.run(tty=True,
                 rm=True,
                 interactive=True,
                 workdir=os.path.join(script_dir, 'test_distributed'),
                 volumes=volumes,
                 reflect=[(script_dir, 'rw'),
                          ('/var/run/docker.sock', 'rw'),
                          (HOST_STORAGE_PATH, 'rw')],
                 name='testmaster_{0}'.format(uid),
                 hostname='testmaster.{0}.test'.format(uid),
                 image=args.image,
                 command=['python', '-c', command])

os.remove(new_cover)
if args.cover:
    for file in env_descs:
        os.remove(file)
        shutil.move(file + '.bak', file)

if ret != 0 and not skipped_test_exists("test_distributed/logs/*/surefire.xml"):
    ret = 0

sys.exit(ret)
