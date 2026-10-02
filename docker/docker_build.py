#!/usr/bin/env python3

# coding=utf-8
"""Author: Krzysztof Trzepla, Jakub Liput
Copyright (C) 2016 ACK CYFRONET AGH
Copyright (C) 2026 Onedata (onedata.org)
This software is released under the MIT license cited in 'LICENSE.txt'

Runs docker build process and publish image to a private docker repository.

Execute the script with -h flag to learn about script's running options.
"""

import argparse
import json
import re
import subprocess
import os

from environment import docker_p3


def cmd(args):
    """Executes shell command and returns result without trailing newline.
    Standard error is redirected to /dev/null."""

    with open('/dev/null', 'w', encoding='utf-8') as dev_null:
        result = subprocess.check_output(args, stderr=dev_null)
    if isinstance(result, bytes):
        result = result.decode()
    return result.rstrip('\n')


def get_repository_name():
    """Returns repository name."""

    remote = cmd(['git', 'remote', '-v'])
    remote = [r for r in remote.split('\n') if r.startswith('origin')]
    return remote[0].split('/')[-1].split('.')[0]


def get_tags():
    """Returns prioritized lists of tags. First tag in the list has the highest
    priority. Each tag is accompanied by its type. Possible types are git-tag,
    git-branch and git-commit."""

    tags = []
    commit = cmd(['git', 'rev-parse', 'HEAD'])
    branch = get_current_branch()

    git_tags = cmd(['git', 'tag', '--points-at', commit]).split('\n')
    git_tags = [tag for tag in git_tags if tag]

    if git_tags:
        tags.append(('git-tag', git_tags[0]))

    tags.append(('git-branch', get_branch_tag(branch)))

    tags.append(('git-commit', 'ID-{0}'.format(commit[0:10])))

    return tags


def get_current_branch():
    if 'bamboo_planRepository_branchName' in os.environ:
        branch_name = os.environ['bamboo_planRepository_branchName']
        print('[INFO] ENV variable "bamboo_planRepository_branchName" is set to {} - using it '
              'as current branch name'.format(branch_name))
    else:
        branch_name = cmd(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    if branch_name == 'HEAD':
        raise ValueError('Could not resolve branch name - repository in detached HEAD state. '
                         'You must run this script on the newest commit of the current branch.')
    return branch_name


def get_branch_tag(branch):
    if branch == 'develop':
        return 'develop'

    ticket = re.search(r'VFS-\d+.*', branch)
    for prefix in ['feature/', 'bugfix/']:
        if branch.startswith(prefix) and ticket:
            return ticket.group(0)
    for prefix in ['release/', 'hotfix/']:
        if branch.startswith(prefix):
            return branch.lstrip(prefix)
    return branch.replace('/', '_')


def write_short_report(file_name, images):
    """Creates a short report consisting of docker images and theirs tag
    types in JSON format."""

    with open(file_name, 'w') as f:
        json.dump(dict(images), f, indent=2)


def write_report(file_name, name, images, publish):
    """Creates a report consisting of built artifacts (docker images) and
    commands describing how to download those artifacts."""

    with open(file_name, 'w') as f:
        f.write('Build report for {0}\n\n'.format(name))
        f.write('Artifacts:\n\n')
        for _, image in images:
            f.write('Artifact {0}\n'.format(image))
            if publish:
                f.write('\tTo get image run:\n')
                f.write('\t\tdocker pull {0}\n\n'.format(image))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Run docker build process and publish results to registry.')

    parser.add_argument(
        '--user',
        action='store',
        help='username used to login to the docker repository',
        dest='user')

    parser.add_argument(
        '--password',
        action='store',
        help='password used to login to the docker repository',
        dest='password')

    parser.add_argument(
        '--repository',
        action='store',
        default='docker.onedata.org',
        help='repository used to publish docker',
        dest='repository')

    parser.add_argument(
        '--report',
        action='store',
        default='docker-build-report.txt',
        help='report file',
        dest='report')

    parser.add_argument(
        '--short-report',
        action='store',
        default='docker-build-list.json',
        help='short report file',
        dest='short_report')

    try:
        parser.add_argument(
            '--name',
            action='store',
            default=get_repository_name(),
            help='name for docker image',
            dest='name')
    except subprocess.CalledProcessError:
        parser.add_argument(
            '--name',
            action='store',
            required=True,
            help='name for docker image',
            dest='name')

    parser.add_argument(
        '--tag',
        action='append',
        default=[],
        help='custom tag for docker image',
        dest='tags')

    parser.add_argument(
        '--publish',
        action='store_true',
        default=False,
        help='publish docker to the repository',
        dest='publish')

    parser.add_argument(
        '--remove',
        action='store_true',
        default=False,
        help='remove local docker image after build',
        dest='remove')

    [args, pass_args] = parser.parse_known_args()
    tags = get_tags()
    tags.extend([('custom-{0}'.format(i), tag) for i, tag in enumerate(
        args.tags)])

    if args.user and args.password:
        docker_p3.login(args.user, args.password, args.repository)

    image = '{0}/{1}:{2}'.format(args.repository, args.name, tags[0][1])

    docker_p3.build_image(image, pass_args)
    images = [(tags[0][0], image)]

    for tag in tags[1:]:
        image_tag = '{0}/{1}:{2}'.format(args.repository, args.name, tag[1])
        docker_p3.tag_image(image, image_tag)
        images.append((tag[0], image_tag))

    unique_images = list(set([x for _,x in images]))
    for image in unique_images:
        if args.publish:
            docker_p3.push_image(image)

        if args.remove:
            docker_p3.remove_image(image)

    write_short_report(args.short_report, images)
    write_report(args.report, args.name, images, args.publish)
