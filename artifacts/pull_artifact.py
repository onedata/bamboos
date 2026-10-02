#! /usr/bin/env python3
"""
Pulls an artifact from external repo. Artifacts are file packages -
typically gzip compressed tarballs.

Artifacts are identified by names, which are assigned during pushing.
If no name is provided, default build artifact name is used.

Build artifacts in the external repo are always named based on the
plan's repo and branch, for example: `op-worker/develop.tar.gz`.
The local name of the build archive is always based on the plan name.
For example: `op_worker.tar.gz` (note that dashes are replaced by underscores).

Artifacts with custom names are placed in a directory depending on
the plan's repo and branch, for example:
`op-worker/feature/VFS-1234-my-branch/custom-artifact.tar.gz`

Run the script with -h flag to learn about script's running options.
"""
__author__ = "Jakub Kudzia, Darin Nikolow"
__copyright__ = "Copyright (C) 2016-2022 ACK CYFRONET AGH"
__license__ = "This software is released under the MIT license cited in " \
              "LICENSE.txt"

import argparse
from paramiko import SSHClient, AutoAddPolicy
from scp import SCPClient
import signal
import sys
import boto3
from typing import Callable, Optional, Any, Tuple
import artifact_utils
from artifact_utils import *
import os


DEVELOP_BRANCH = 'develop'


def parse_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Push build artifacts.')

    parser.add_argument(
        '--hostname', '-hn',
        help='Hostname of artifacts repository',
        required=True)

    parser.add_argument(
        '--port', '-p',
        type=int,
        help='SSH port to connect to',
        required=True)

    parser.add_argument(
        '--username', '-u',
        help='The username to authenticate as',
        required=True)

    parser.add_argument(
        '--branch', '-b',
        help='Name of current git branch',
        required=True)

    parser.add_argument(
        '--plan', '-pl',
        help='Name of current bamboo plan',
        required=True)

    parser.add_argument(
        '--artifact-name', '-an',
        help='Name of the artifact to be pulled, corresponding to the name used during artifact push. ',
        default=None,
        required=False)

    parser.add_argument(
        '--target-file-path', '-tf',
        help='Location where the pulled artifact will be saved. Defaults to the artifact name in CWD.',
        default=None,
        required=False)
    
    parser.add_argument(
        '--s3-url',
        help='The S3 endpoint URL',
        default='https://storage.cloud.cyfronet.pl')

    parser.add_argument(
        '--s3-bucket',
        help='The S3 bucket name',
        default='bamboo-artifacts-2')
    
    parser.add_argument(
        '--fallback-branch',
        help='Name of git branch to which script will fallback if artifact for desired ' +
             'branch is not found',
        default=DEVELOP_BRANCH)

    return parser.parse_args()


def download_specific_or_default(ssh: SSHClient, plan: str, branch: str, artifact: str,
                                 target_file_path: str, hostname: str, port: int, username: str,
                                 fallback_branch: str = DEVELOP_BRANCH) -> None:
    download_artifact_safe(
        ssh, plan, branch, artifact, target_file_path, hostname, port, username,
        exc_handler=download_default_artifact,
        exc_handler_args=(ssh, plan, fallback_branch, artifact, target_file_path, hostname, port,
                          username),
        exc_log="Artifact of plan {0}, specific for branch {1} not found, "
                "pulling artifact from branch {2}.".format(plan, branch,
                                                           fallback_branch))

    
def s3_download_specific_or_default(s3: boto3.resources, bucket: str, plan: str, branch: str,
                                    artifact: str, target_file_path: str,
                                    fallback_branch: str = DEVELOP_BRANCH) -> None:
    s3_download_artifact_safe(
        s3, bucket, plan, branch, artifact, target_file_path,
        exc_handler=s3_download_default_artifact,
        exc_handler_args=(s3, bucket, plan, fallback_branch, artifact, target_file_path),
        exc_log="Artifact of plan {0}, specific for branch {1} not found, "
                "pulling artifact from branch {2}.".format(plan, branch,
                                                           fallback_branch))

    
def download_default_artifact(ssh: SSHClient, plan: str, branch: str, artifact: str,
                              target_file_path: str, hostname: str, port: int, username: str) -> None:
    download_artifact_safe(
        ssh, plan, branch, artifact, target_file_path, hostname, port, username,
        exc_log="Pulling artifact of plan {}, from branch {} failed."
                .format(plan, branch))

    
def s3_download_default_artifact(s3: boto3.resources, bucket: str,
                                 plan: str, branch: str, artifact: str, target_file_path: str) -> None:
    s3_download_artifact_safe(
        s3, bucket, plan, branch, artifact, target_file_path,
        exc_log="Pulling artifact of plan {}, from branch {} failed."
                .format(plan, branch))

    
def download_artifact_safe(ssh: SSHClient, plan: str, branch: str, artifact: str,
                           target_file_path: str, hostname: str, port: int, username: str,
                           exc_handler: Optional[Callable[..., Any]] = None,
                           exc_handler_args: Tuple[Any, ...] = (),
                           exc_log: str = '') -> None:
    """
    Downloads artifact from repo. Locks file while it's being downloaded.
    If exception is thrown during download, exc_log is printed and
    exc_handler function is called.
    """

    def signal_handler(_signum, _frame):
        ssh.connect(hostname, port=port, username=username)
        sys.exit(1)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        download_artifact(ssh, plan, branch, artifact, target_file_path)
    except Exception as ex:
        print(exc_log)
        if exc_handler:
            return exc_handler(*exc_handler_args)
        else: 
            print('Unexpected error: {}'.format(ex))
            sys.exit(1)

            
def s3_download_artifact_safe(s3: boto3.resources, bucket: str,
                              plan: str, branch: str, artifact: str,
                              target_file_path: str,
                              exc_handler: Optional[Callable[..., Any]] = None,
                              exc_handler_args: Tuple[Any, ...] = (),
                              exc_log: str = '') -> None:
    """
    Downloads artifact from repo. Locks file while it's being downloaded.
    If exception is thrown during download, exc_log is printed and
    exc_handler function is called.
    """

    def signal_handler(_signum, _frame):
        sys.exit(1)

    signal.signal(signal.SIGINT, signal_handler)

    try:        
        s3_download_artifact(s3, bucket, plan, branch, artifact, target_file_path)
    except Exception as ex:
        print(exc_log)
        if exc_handler:
            return exc_handler(*exc_handler_args)
        else: 
            print('Unexpected error: {}'.format(ex))
            sys.exit(1)


def download_artifact(ssh: SSHClient, plan: str, branch: str, artifact_name: str, target_file_path: str) -> None:
    dst_path = artifact_utils.build_local_path(target_file_path, artifact_name, plan)
    src_path = artifact_utils.build_repo_path(artifact_name, plan, branch)
    print("Pulling artifact for branch '{}' from repo path: '{}' ...".format(branch, src_path))
    with SCPClient(ssh.get_transport()) as scp:
        scp.get(src_path, local_path=dst_path)

        
def s3_download_artifact(s3: boto3.resources, bucket: str, plan: str,
                         branch: str, artifact_name: str, target_file_path: str) -> None:
    buck = s3.Bucket(bucket)
    dst_path = artifact_utils.build_local_path(target_file_path, artifact_name, plan)
    src_path = artifact_utils.build_repo_path(artifact_name, plan, branch)
    print("Pulling artifact for branch '{}' from repo path: '{}' ...".format(branch, src_path))
    buck.download_file(src_path, dst_path)


def main():
    args = parse_args()
    if args.hostname != 'S3':
        ssh = SSHClient()
        ssh.set_missing_host_key_policy(AutoAddPolicy())
        ssh.load_system_host_keys()
        ssh.connect(args.hostname, port=args.port, username=args.username)

        download_specific_or_default(ssh, args.plan, args.branch, args.artifact_name,
                                     args.target_file_path, args.hostname, args.port,
                                     args.username, args.fallback_branch)

        ssh.close()
    else:
        # Define the standard path to AWS credentials
        # os.path.expanduser("~") ensures this works on both Linux/Mac and Windows
        creds_path = os.path.expanduser("~/.aws/credentials")

        if os.path.exists(creds_path):
            # Use the default credentials from the file
            print("Found ~/.aws/credentials. Using local profile.")
            s3_session = boto3.Session()
            s3_res = s3_session.resource(
                service_name='s3',
                endpoint_url=args.s3_url
            )
        else:
            # Use hardcoded s3proxy as a fallback
            print("Credentials file not found. Usung s3proxy.onedata.org.")
            s3_session = boto3.Session(
                aws_access_key_id='dummy',
                aws_secret_access_key='dummy'
            )
            s3_res = s3_session.resource(
                service_name='s3',
                endpoint_url='https://s3proxy.onedata.org'
            )
        s3_download_specific_or_default(s3_res, args.s3_bucket, args.plan, args.branch,
                                        args.artifact_name, args.target_file_path, args.fallback_branch)


if __name__ == '__main__':
    main()
