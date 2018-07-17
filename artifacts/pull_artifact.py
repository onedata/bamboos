#! /usr/bin/env python3
"""
Pulls build artifact from external repo.

Run the script with -h flag to learn about script's running options.
"""
__author__ = "Jakub Kudzia"
__copyright__ = "Copyright (C) 2016-2018 ACK CYFRONET AGH"
__license__ = "This software is released under the MIT license cited in " \
              "LICENSE.txt"

import argparse
from paramiko import SSHClient, AutoAddPolicy
from scp import SCPClient
import signal
import sys

from artifact_utils import artifact_path, ARTIFACTS_EXT, DEVELOP_BRANCH


def download_specific_or_default(ssh, plan, branch, hostname, port, username,
                                 default_branch=DEVELOP_BRANCH):
    """
    Downloads build artifact for specific plan and branch from repo.
    If artifact doesn't exist in repo, artifact from default (develop) branch
    is downloaded.
    :param ssh: sshclient with opened connection
    :type ssh: paramiko.SSHClient
    :param plan: name of current bamboo plan
    :type plan: str
    :param branch: name of current git branch
    :type branch: str
    :param hostname: hostname of artifacts repository
    :type hostname: str
    :param port: SSH port
    :type port: int
    :param username: username to authenticate as
    :type username: str
    :param default_branch: name of default git branch
    :type default_branch: str
    :return None
    """
    download_artifact_safe(
        ssh, plan, branch, hostname, port, username,
        exception_handler=download_default_artifact,
        exception_handler_args=(ssh, plan, default_branch, hostname, port,
                                username),
        exception_log=
        "Artifact of plan {0}, specific for branch {1} not found"
        ", pulling artifact from branch {}.".format(plan, branch,
                                                    default_branch))


def download_default_artifact(ssh, plan, branch, hostname, port, username):
    """
    Downloads build artifact for specific plan from default branch.
    :param ssh: sshclient with opened connection
    :type ssh: paramiko.SSHClient
    :param plan: name of current bamboo plan
    :type plan: str
    :param branch: name of git branch
    :type branch: str
    :param hostname: hostname of artifacts repository
    :type hostname: str
    :param port: SSH port
    :type port: int
    :param username: username to authenticate as
    :type username: str
    :return None
    """
    download_artifact_safe(
        ssh, plan, branch, hostname, port, username,
        exception_log="Pulling artifact of plan {}, from branch {} "
                      "failed.".format(plan, branch))


def download_artifact_safe(ssh, plan, branch, hostname, port, username,
                           exception_handler=None, exception_handler_args=(),
                           exception_log=""):
    """
    Downloads artifact from repo. Locks file while it's being downloaded.
    If exception is thrown during download, exception_log is printed and
    exception_handler function is called.
    :param ssh: sshclient with opened connection
    :type ssh: paramiko.SSHClient
    :param plan: name of current bamboo plan
    :type plan: str
    :param branch: name of current git branch
    :type branch: str
    :param hostname: hostname of artifacts repository
    :type hostname: str
    :param port: SSH port
    :type port: int
    :param username: username to authenticate as
    :type username: str
    :param exception_handler: function called when exception is thrown while
    artifact is being downloaded
    :type exception_handler: function
    :param exception_handler_args: args for exception_handler
    :type exception_handler_args: tuple
    :param exception_log: log that is printed when exception is thrown while
    artifact is being downloaded
    :type exception_log: str
    :return None
    """

    def signal_handler(_signum, _frame):
        ssh.connect(hostname, port=port, username=username)
        sys.exit(1)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        download_artifact(ssh, plan, branch)
    except:
        print(exception_log)
        if exception_handler:
            exception_handler(*exception_handler_args)


def download_artifact(ssh, plan, branch):
    """
    Downloads artifact from repo via SCP protocol.
    :param ssh: sshclient with opened connection
    :type ssh: paramiko.SSHClient
    :param plan: name of current bamboo plan
    :type plan: str
    :param branch: name of current git branch
    :type branch: str
    :return None
    """
    with SCPClient(ssh.get_transport()) as scp:
        scp.get(artifact_path(plan, branch),
                local_path=plan.replace("-", '_') + ARTIFACTS_EXT)


parser = argparse.ArgumentParser(
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    description='Push build artifacts.')

parser.add_argument(
    '--hostname', '-hn',
    action='store',
    help='Hostname of artifacts repository',
    dest='hostname',
    required=True)

parser.add_argument(
    '--port', '-p',
    action='store',
    type=int,
    help='SSH port to connect to',
    dest='port',
    required=True)

parser.add_argument(
    '--username', '-u',
    action='store',
    help='The username to authenticate as',
    dest='username',
    required=True)

parser.add_argument(
    '--branch', '-b',
    action='store',
    help='Name of current git branch',
    dest='branch',
    required=True)

parser.add_argument(
    '--plan', '-pl',
    action='store',
    help='Name of current bamboo plan',
    dest='plan',
    required=True)


def main():
    args = parser.parse_args()

    ssh = SSHClient()
    ssh.set_missing_host_key_policy(AutoAddPolicy())
    ssh.load_system_host_keys()
    ssh.connect(args.hostname, port=args.port, username=args.username)

    download_specific_or_default(ssh, args.plan, args.branch, args.hostname,
                                 args.port, args.username)

    ssh.close()


if __name__ == '__main__':
    main()
