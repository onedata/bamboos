# coding=utf-8
"""Author: Lukasz Opiola
Copyright (C) 2018 ACK CYFRONET AGH
This software is released under the MIT license cited in 'LICENSE.txt'

Utility module to decide which docker images should be used across bamboos
scripts. Supported image types (passed as string):

    * builder
    * worker
    * dns
    * ceph
    * cephrados
    * s3
    * swift
    * glusterfs
    * webdav
    * xrootd
    * nfs
    * http

To override an image using a config file, place a json file called
'dockers.config' anywhere on the path from CWD to the executed bamboos script.
The file should contain simple key-value pairs, with keys being types of
dockers to use in bamboos scripts. Example 'dockers.config' content:
{
    "builder": "onedata/builder:1902-1",
    "worker": "onedata/worker:1902-1"
}

Images can also be overriden using ENV variables
(they have the highest priority):

    * BUILDER_IMAGE
    * WORKER_IMAGE
    * DNS_IMAGE
    * CEPH_IMAGE
    * CEPHRADOS_IMAGE
    * S3_IMAGE
    * SWIFT_IMAGE
    * GLUSTERFS_IMAGE
    * WEBDAV_IMAGE
    * XROOTD_IMAGE
    * NFS_IMAGE
    * HTTP_IMAGE
"""

import sys
import os
import json

DOCKERS_CONFIG_FILE = 'dockers.config'


def default_image(type):
    # those two dockers do not have a sane default; force the user to specify the right image
    if type == 'builder' or type == 'worker':
        print('ERROR: no image specified for the {} image in dockers.config nor {} ENV, exiting'.format(
            type, image_override_env(type)
        ))
        sys.exit(1)
    return {
        'dns': 'onedata/dns',
        'ceph': 'onedata/ceph',
        'cephrados': 'onedata/ceph',
        's3': 'onedata/minio:v1',
        'swift': 'onedata/dockswift',
        'glusterfs': 'onedata/glusterfs:v1',
        'webdav': 'onedata/sabredav:v1',
        'xrootd': 'onedata/xrootd:v2',
        'nfs': 'onedata/nfs:v1',
        'http': 'onedata/lighttpd:v1'
    }[type]


def image_override_env(type):
    return {
        'builder': 'BUILDER_IMAGE',
        'worker': 'WORKER_IMAGE',
        'dns': 'DNS_IMAGE',
        'ceph': 'CEPH_IMAGE',
        'cephrados': 'CEPHRADOS_IMAGE',
        's3': 'S3_IMAGE',
        'swift': 'SWIFT_IMAGE',
        'glusterfs': 'GLUSTERFS_IMAGE',
        'webdav': 'WEBDAV_IMAGE',
        'xrootd': 'XROOTD_IMAGE',
        'nfs': 'NFS_IMAGE',
        'http': 'HTTP_IMAGE'
    }[type]


def filesystem_root():
    return os.path.abspath(os.sep)


def ensure_image(args, arg_name, type):
    if arg_name in vars(args) and vars(args)[arg_name]:
        print('Using commandline image for {}: {}'.format(type,
                                                          vars(args)[arg_name]))
        return
    else:
        vars(args)[arg_name] = get_image(type)


def get_image(type):
    if image_override_env(type) in os.environ:
        image = os.environ[image_override_env(type)]
        print('Using overriden image for {}: {}'.format(type, image))
        return image

    # look for DOCKERS_CONFIG_FILE starting from the place where the script is
    # called (potentially the repo that includes bamboos as submodule)
    start_path = os.getcwd()
    end_path = filesystem_root()
    image = search_for_config_with_entry(start_path, end_path, type)
    if image:
        return image

    # otherwise look for entry in default DOCKERS_CONFIG_FILE in bamboos repo
    start_path = os.path.realpath(__file__)
    image = search_for_config_with_entry(start_path, end_path, type)
    if image:
        return image

    # if all methods fail, return the default image defined statically
    image = default_image(type)
    print('Using default image for {}: {}'.format(type, image))
    return image


def search_for_config_with_entry(current_path, end_path, type):
    cfg_path = os.path.join(current_path, DOCKERS_CONFIG_FILE)
    if os.path.isfile(cfg_path):
        config = json.load(open(cfg_path))
        if type in config:
            image = config[type]
            print('Found dockers config in {}'.format(os.path.normpath(cfg_path)))
            print('Using preconfigured image for {}: {}'.format(type, image))
            return image

    if current_path == end_path:
        return None

    # Step one dir upwards
    current_path = os.path.dirname(current_path)
    return search_for_config_with_entry(current_path, end_path, type)
