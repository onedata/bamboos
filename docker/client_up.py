#!/usr/bin/env python
# coding=utf-8

"""Authors: Łukasz Opioła, Konrad Zemek
Copyright (C) 2015 ACK CYFRONET AGH
This software is released under the MIT license cited in 'LICENSE.txt'

A script that prepares a set dockers with oneclient instances that are
configured and ready to start.
Run the script with -h flag to learn about script's running options.
"""


import json

from environment import client, common, dockers_config


parser = common.standard_arg_parser(
    'Set up dockers with oneclient preconfigured.')
parser.add_argument(
    '-i-', '--image',
    action='store',
    default=None,
    help='docker image to use for the container',
    dest='image')
parser.add_argument(
    '-l', '--logdir',
    action='store',
    default=None,
    help='path to a directory where the logs will be stored',
    dest='logdir')

args = parser.parse_args()
dockers_config.ensure_image(args, 'image', 'worker')

output = client.up(args.image, args.bin, args.dns, args.uid,
                   args.config_path, args.logdir)

print(json.dumps(output))
