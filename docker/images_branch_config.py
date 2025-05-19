"""
Module used for manipulating branch config.
Branch config is a yaml file in following format:

    default: develop
    images:
      onezone: current_branch
      oneprovider: some_branch

Allowed images keys: [
    onezone, oneprovider, oneclient, rest-cli,
    openfaas-pod-status-monitor, openfaas-lambda-result-streamer
]
Allowed values: current_branch, default(only under `images` key), release/{version},
                {any image tag}, {any branch name}
"""
__author__ = "Michal Stanisz"
__copyright__ = "Copyright (C) 2022 ACK CYFRONET AGH"
__license__ = "This software is released under the MIT license cited in " \
              "LICENSE.txt"

import os
import yaml

from docker_build import get_current_branch, get_branch_tag
from environment import docker

SERVICE_TO_IMAGE = {
    'onezone': 'docker.onedata.org/onezone-dev',
    'oneprovider': 'docker.onedata.org/oneprovider-dev',
    'oneclient': 'docker.onedata.org/oneclient-dev',
    'rest-cli': 'docker.onedata.org/rest-cli',
    'openfaas-pod-status-monitor': 'docker.onedata.org/openfaas-pod-status-monitor',
    'openfaas-lambda-result-streamer': 'docker.onedata.org/openfaas-lambda-result-streamer'
}


def resolve_image(service):
    """Returns service image based on branch from branchConfig.yaml file"""
    branch_config_path = os.path.join(os.getcwd(), 'branchConfig.yaml')
    try:
        with open(branch_config_path, 'r') as branch_config_file:
            branch_config = yaml.load(branch_config_file, yaml.Loader)

            fallback_branch = branch_config['default']
            fallback_tag = get_branch_tag(fallback_branch)

            service_branch = branch_config['images'].get(service)
            if not service_branch:
                return None
            elif service_branch == 'current_branch':
                branch = get_current_branch()
                branch_tag = get_branch_tag(branch)
            elif service_branch == 'default':
                branch_tag = fallback_tag
            else:
                branch_tag = get_branch_tag(service_branch)

            image = '{}:{}'.format(SERVICE_TO_IMAGE[service], branch_tag)
            fallback_image = '{}:{}'.format(SERVICE_TO_IMAGE[service], fallback_tag)
            if docker.image_exists(image):
                return image
            else:
                print('\n[INFO] Image {} for service {} not found. Falling back to {}'.format(
                    image, service, fallback_image))
                return fallback_image
    except (IOError, KeyError) as e:
        print("[ERROR] Error when reading image for {} from branch config file {}: {}.".format(
            service, branch_config_path, e))
        raise e
