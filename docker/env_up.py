#!/usr/bin/env python3
# coding=utf-8

"""Author: Łukasz Opioła
Copyright (C) 2015 ACK CYFRONET AGH
This software is released under the MIT license cited in 'LICENSE.txt'

Brings up dockers with full onedata environment.
Run the script with -h flag to learn about script's running options.
"""



import argparse
import json

from environment import env, dockers_config

parser = argparse.ArgumentParser(
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    description='Bring up onedata environment.')

parser.add_argument(
    '-i', '--image',
    action='store',
    default=None,
    help='override of docker image for onedata components',
    dest='image')

parser.add_argument(
    '-ci', '--ceph-image',
    action='store',
    default=None,
    help='override of docker image for ceph storages',
    dest='ceph_image')

parser.add_argument(
    '-si', '--s3-image',
    action='store',
    default=None,
    help='override of docker image for s3 storages',
    dest='s3_image')

parser.add_argument(
    '-gi', '--glusterfs-image',
    action='store',
    default=None,
    help='override of docker image for GlusterFS storages',
    dest='glusterfs_image')

parser.add_argument(
    '-wi', '--webdav-image',
    action='store',
    default=None,
    help='override of docker image for WebDAV storages',
    dest='webdav_image')

parser.add_argument(
    '-xi', '--xrootd-image',
    action='store',
    default=None,
    help='override of docker image for XRootD storages',
    dest='xrootd_image')

parser.add_argument(
    '-ni', '--nfs-image',
    action='store',
    default=None,
    help='override of docker image for NFS storages',
    dest='nfs_image')

parser.add_argument(
    '-hi', '--http-image',
    action='store',
    default=None,
    help='override of docker image for HTTP storages',
    dest='http_image')

parser.add_argument(
    '-bw', '--bin-worker',
    action='store',
    default=env.default('bin_op_worker'),
    help='the path to op_worker repository (precompiled)',
    dest='bin_op_worker')

parser.add_argument(
    '-bcw', '--bin-cluster-worker',
    action='store',
    default=env.default('bin_cluster_worker'),
    help='the path to cluster_worker repository (precompiled)',
    dest='bin_cluster_worker')

parser.add_argument(
    '-bcm', '--bin-cm',
    action='store',
    default=env.default('bin_cluster_manager'),
    help='the path to cluster_manager repository (precompiled)',
    dest='bin_cluster_manager')

parser.add_argument(
    '-boz', '--bin-oz',
    action='store',
    default=env.default('bin_oz'),
    help='the path to zone repository (precompiled)',
    dest='bin_oz')

parser.add_argument(
    '-bop', '--bin-onepanel',
    action='store',
    default=env.default('bin_onepanel'),
    help='the path to onepanel repository (precompiled)',
    dest='bin_onepanel')

parser.add_argument(
    '-ba', '--bin-appmock',
    action='store',
    default=env.default('bin_am'),
    help='the path to appmock repository (precompiled)',
    dest='bin_am')

parser.add_argument(
    '-bc', '--bin-client',
    action='store',
    default=env.default('bin_oc'),
    help='the path to oneclient repository (precompiled)',
    dest='bin_oc')

parser.add_argument(
    '-l', '--logdir',
    action='store',
    default=env.default('logdir'),
    help='path to a directory where the logs will be stored',
    dest='logdir')

parser.add_argument(
    'config_path',
    action='store',
    help='path to json configuration file')

args = parser.parse_args()
dockers_config.ensure_image(args, 'image', 'worker')
dockers_config.ensure_image(args, 'ceph_image', 'ceph')
dockers_config.ensure_image(args, 's3_image', 's3')
dockers_config.ensure_image(args, 'glusterfs_image', 'glusterfs')
dockers_config.ensure_image(args, 'webdav_image', 'webdav')
dockers_config.ensure_image(args, 'xrootd_image', 'xrootd')
dockers_config.ensure_image(args, 'nfs_image', 'nfs')
dockers_config.ensure_image(args, 'http_image', 'http')

output = env.up(args.config_path, image=args.image, ceph_image=args.ceph_image,
                s3_image=args.s3_image, glusterfs_image=args.glusterfs_image,
                webdav_image=args.webdav_image,
                xrootd_image=args.xrootd_image,
                nfs_image=args.nfs_image,
                http_image=args.http_image,
                bin_am=args.bin_am, bin_oz=args.bin_oz,
                bin_cluster_manager=args.bin_cluster_manager,
                bin_op_worker=args.bin_op_worker,
                bin_cluster_worker=args.bin_cluster_worker,
                bin_onepanel=args.bin_onepanel,
                bin_oc=args.bin_oc, logdir=args.logdir)

print(json.dumps(output))
