#!/bin/bash

# Authors: Darin Nikolow
# Copyright (C) 2022 ACK CYFRONET AGH
# This software is released under the MIT license cited in 'LICENSE.txt'

# Usage: ./run-build.sh <PLAN_TO_RUN> 
# 
# This script runs a new build of PLAN_TO_RUN.
# The script resides on the bamboo server in /home/ubuntu/bin.
#
# .bamboo-creds contains the necessary credentials. Example content:
#
#   export BAMBOO_CREDS=bamboo_user:password
#
. /home/ubuntu/.bamboo-creds

PLAN_TO_RUN=$1

curl -s -u $BAMBOO_CREDS -X POST -H "Accept: application/json" http://localhost:8085/rest/api/latest/queue/${PLAN_TO_RUN}




