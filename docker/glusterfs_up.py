#!/usr/bin/env python
# coding=utf-8

"""Authors: Bartek Kryza
Copyright (C) 2017 ACK CYFRONET AGH
This software is released under the MIT license cited in 'LICENSE.txt'

A script that brings up a GlusterFS storage.
Run the script with -h flag to learn about script's running options.
"""



import argparse
import json

from environment import common, dockers_config

parser = argparse.ArgumentParser(
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    description='Bring up GlusterFS storage.')

parser.add_argument(
    '-i', '--image',
    action='store',
    default=None,
    help='docker image to use for the container',
    dest='image')

parser.add_argument(
    '-v', '--volume',
    action='append',
    default=[],
    help='bucket name',
    dest='buckets')

parser.add_argument(
    '-u', '--uid',
    action='store',
    default=common.generate_uid(),
    help='uid that will be concatenated to docker names',
    dest='uid')

parser.add_argument(
    '-t', '--transport',
    action='store',
    default="tcp",
    help='Type of communication transport for volume file server: "socket", "tcp" or "rdma"',
    dest='transport')

args = parser.parse_args()
dockers_config.ensure_image(args, 'image', 'glusterfs')
config = glusterfs.up(args.image, args.volumes, 'storage', args.uid, args.transport)

print(json.dumps(config))
