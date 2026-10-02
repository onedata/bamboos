"""Common utilities for running common tests using one-env."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2023 ACK CYFRONET AGH"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"


import argparse
import glob
import os
import platform
import sys
import xml.etree.ElementTree as ElementTree
from os.path import expanduser

import images_branch_config
from environment import docker


CONFIG_DIRS = [".docker", ".kube", ".minikube/profiles", ".one-env"]

DOCKER_CMD_TEMPLATE = """
import os, shutil, subprocess, sys, stat

home = '{user_home}'
os.environ['HOME'] = home
if not os.path.exists(home):
    os.makedirs(home, exist_ok=True)

if {shed_privileges}:
    os.environ['PATH'] = os.environ['PATH'].replace('sbin', 'bin')
    os.chown(home, {uid}, {gid})
    docker_gid = os.stat('/var/run/docker.sock').st_gid
    os.chmod('/etc/hosts', 0o666)
    os.chmod('/etc/resolv.conf', 0o666)
    os.setgroups([docker_gid])
    os.setregid({gid}, {gid})
    os.setreuid({uid}, {uid})

config_dirs={config_dirs}

def ignore_files(dir_path, _children):
    if dir_path == '/tmp/.minikube':
        # ignore (when copying) not used but potentially large dirs 
        # (e.g. in case of virtualbox machines/ may have ~20GB)
        return ['machines', 'cache']

    return []

# Try to copy config dirs, continue if it fails (might not exist on host).
for dirname in config_dirs:
    try:
        shutil.copytree(
            os.path.join('/tmp', dirname), 
            os.path.join(home, dirname),
            ignore=ignore_files
        )
    except:
        pass

ct_cmd = {ct_cmd}

ct_env = os.environ.copy()
ct_env.update({ct_env})

ret = subprocess.run(ct_cmd, env=ct_env).returncode

import xml.etree.ElementTree as ElementTree, glob, re
for file in glob.glob('**/logs/*/surefire.xml', recursive=True):
    tree = ElementTree.parse(file)
    for suite in tree.findall('.//testsuite'):
        for test in suite.findall('testcase'):
            match = re.match('(init|end)_per_(suite|group)', test.attrib['name'])
            if match is not None:
                suite.remove(test)
            elif test.get('group'):
                # A suite may run the same case function in several groups, each
                # supplying a different parametrisation. Report readers key on
                # classname/name (Bamboo displays them as "classname name" and
                # falls back to the suite name when classname is absent), so the
                # group is appended to the suite name - 'suite:group' - rather
                # than replacing it. Nested groups, which CT joins with dots, are
                # joined with colons as well, so that the classname is never
                # mistaken for a package qualified one.
                classname = ':'.join([suite.attrib['name']] + test.attrib['group'].split('.'))
                test.set('classname', classname)
    tree.write(file)

sys.exit(ret)
"""


def parse_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Run Common Tests.",
    )

    parser.add_argument(
        "--image",
        "-i",
        action="store",
        default=None,
        help="override of docker image to use as test master.",
        dest="image",
    )

    parser.add_argument(
        "--suite",
        "-s",
        default=[],
        action="append",
        help="name of the test suite (can be repeated)",
        dest="suites",
    )

    parser.add_argument(
        "--group",
        "-g",
        default=[],
        action="append",
        help="name of the test group (can be repeated)",
        dest="groups",
    )

    parser.add_argument(
        "--case",
        "-c",
        default=[],
        action="append",
        help="name of the test case (can be repeated)",
        dest="cases",
    )

    parser.add_argument(
        "--performance",
        "-p",
        action="store_true",
        default=False,
        help="run performance tests",
        dest="performance",
    )

    parser.add_argument(
        "--cover",
        action="store_true",
        default=False,
        help="run cover analysis",
        dest="cover",
    )

    parser.add_argument(
        "--path-to-sources",
        default=os.path.normpath(os.path.join(os.getcwd(), "..")),
        help=(
            "path to sources to be mounted in onenv container. "
            "Use when sources are outside $HOME directory"
        ),
        dest="path_to_sources",
    )

    parser.add_argument(
        "-sf",
        "--sources-filter",
        action="append",
        help="Sources filter passed to onenv up script. Can be provided multiple times.",
    )

    parser.add_argument(
        "-zi", "--onezone-image", help="onezone image to use", dest="onezone_image"
    )

    parser.add_argument(
        "-pi",
        "--oneprovider-image",
        help="oneprovider image to use",
        dest="oneprovider_image",
    )

    parser.add_argument(
        "--no-pull",
        action="store_true",
        help=(
            "By default all tests scenarios force pulling docker images "
            "even if they are already present on host machine. When this "
            "option is passed no images will be downloaded."
        ),
        dest="no_pull",
    )

    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="if set environment will not be cleaned up after tests",
        dest="no_clean",
    )

    parser.add_argument(
        "--rsync",
        action="store_true",
        help="use rsync instead of local volume mount for deployments from sources",
        dest="rsync",
    )

    return parser.parse_args()


def get_docker_volumes():
    volumes = []
    for dir_name in CONFIG_DIRS:
        dir_path = expanduser(os.path.join("~", dir_name))
        if os.path.isdir(dir_path):
            volumes.append((dir_path, os.path.join("/tmp", dir_name), "ro"))

    return volumes


def get_docker_command(ct_cmd, ct_env):
    python_cmd = DOCKER_CMD_TEMPLATE.format(
        uid=os.geteuid(),
        gid=os.getegid(),
        ct_cmd=ct_cmd,
        ct_env=ct_env,
        user_home=expanduser("~"),
        config_dirs=CONFIG_DIRS,
        shed_privileges=(platform.system() == "Linux"),
    )

    return ["python3", "-c", python_cmd]


def prepare_ct_environment(args):
    env = {
        "path_to_sources": os.path.normpath(
            os.path.join(os.getcwd(), args.path_to_sources)
        ),
        "clean_env": "false" if args.no_clean else "true",
        "rsync": "true" if args.rsync else "false",
        "cover": "true" if args.cover else "false",
    }

    force_pull = not args.no_pull
    set_image_env_if_defined(env, args.onezone_image, "onezone", force_pull)
    set_image_env_if_defined(env, args.oneprovider_image, "oneprovider", force_pull)

    if args.sources_filter:
        env["sources_filters"] = ";".join(args.sources_filter)

    if args.performance:
        env["performance"] = "true"

    return env


def set_image_env_if_defined(env, image, service_name, force_pull):
    image = image or images_branch_config.resolve_image(service_name)

    if image:
        print(f"\n[INFO] Using image {image} for service {service_name}")

        if force_pull:
            docker.pull_image_with_retries(image)

        env[f"{service_name}_image"] = image


def find_suite_file(name):
    for root, _dirs, files in os.walk("test_distributed"):
        if name in files:
            return os.path.relpath(os.path.join(root, name), "test_distributed")

    print(
        f"ERROR: Suite with name {name} has not been found in the test_distributed directory"
    )

    sys.exit(1)


def any_test_skipped(junit_report_path):
    reports = glob.glob(junit_report_path)
    # if there are many reports, check only the last one
    reports.sort()
    tree = ElementTree.parse(reports[-1])

    return any(test_suite.attrib["skipped"] != "0" for test_suite in tree.getroot())
