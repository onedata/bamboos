#!/bin/bash
###-------------------------------------------------------------------
### @author Lukasz Opiola, Darin Nikolow
### @copyright (C) 2021 ACK CYFRONET AGH
### @copyright (C) 2026: Onedata (onedata.org)
### This software is released under the MIT license
### cited in 'LICENSE.txt'.
### @end
###-------------------------------------------------------------------
### @doc
### This script iterates through a static list of all repos that include one-env
### as a submodule and bumps it to the HEAD of given branch, creating a commit
### and pushing the changes. The list of repos must be manually maintained -
### whenever a new repo with bamboos is added, it should be added here too.
### See bump-common.sh for details.
###
### @end
###-------------------------------------------------------------------

SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" && pwd -P)

. ${SCRIPT_DIR}/bump-common.sh

ALL_REPOS=(
    oneclient
    onepanel
    op-worker
    oz-worker
    onedatarestfs
    fs.onedatafs
    onedata-acceptance
    onedatarestfsspec
)

bump one-env
