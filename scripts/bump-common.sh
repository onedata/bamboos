#!/bin/bash
###-------------------------------------------------------------------
### @author Lukasz Opiola, Darin Nikolow
### @copyright (C) 2021 ACK CYFRONET AGH
### This software is released under the MIT license
### cited in 'LICENSE.txt'.
### @end
###-------------------------------------------------------------------
### @doc
### This script is included by bump-*-in-all-repos.sh scripts.
### It provides the bump() function which takes one argument - the REPO to be
### bumped. The function iterates through a static list of all repos that include bamboos
### as a submodule and bumps it to the HEAD of given branch, creating a commit
### and pushing the changes.
###
### Can be run for the develop branch, in such case it requires permissions to
### push changes directly to develop (intended to be run within a bamboo
### automated job).
###
### By default, the bump() function will bump the REPO ref to the HEAD of
### `TARGET_BRANCH_NAME` (1st argument) only in repos for which the branch
### with the same name exists - otherwise, they will be skipped.
### Using the `CREATE_MISSING_BRANCHES` and `BASE_BRANCH_NAME` env variables,
### it is possible to automatically create the branch `TARGET_BRANCH_NAME` in
### repos where it does not exist.
### @end
###-------------------------------------------------------------------

set -e

USER_NAME=${2:-$(git config user.name)}
USER_NAME=${USER_NAME:-"Bamboo Agent"}
USER_EMAIL=${3:-$(git config user.email)}
USER_EMAIL=${USER_EMAIL:-"bamboo@bamboo.onedata.org"}

TARGET_BRANCH_NAME=${1}
if [ -z "${TARGET_BRANCH_NAME}" ]; then
    echo "Please provide the target branch name in the first argument. "
    echo "The branch will be created (if non-existent) in all repos and the "
    echo "bamboos submodule will be checked out to HEAD of this branch."
    exit 1
fi

# In case the target branch does not exist in a repo, it will be automatically
# created if this variable is set to true.
CREATE_MISSING_BRANCHES=${CREATE_MISSING_BRANCHES:-false}
# If the target branch is to be created, it will be based off this branch.
BASE_BRANCH_NAME=${BASE_BRANCH_NAME:-"develop"}

bump() {
    local BUMP_REPO=${1}
    echo "Bumping ${BUMP_REPO} submodule to HEAD of branch '${TARGET_BRANCH_NAME}' in all repos!"

    WORK_DIR="$(mktemp -d)"
    echo "Entering a tmp working directory: ${WORK_DIR}"
    cd "${WORK_DIR}"

    for REPO in "${ALL_REPOS[@]}"; do
	echo " "
	echo "-------------------------------------------------------------------------"
	echo " "
	git clone "ssh://git@git.onedata.org:7999/vfs/${REPO}.git"
	cd "${REPO}"

	git checkout "${TARGET_BRANCH_NAME}" || {
            if [ "$CREATE_MISSING_BRANCHES" = false ] ; then
		echo ""
		echo "[SKIPPED] Target branch '${TARGET_BRANCH_NAME}' does not exist in repo '${REPO}' - skipping!"
		echo "Consider using 'CREATE_MISSING_BRANCHES' and 'BASE_BRANCH_NAME' env variables to automatically create missing branches."
		cd ..
		continue
            else
		git checkout "${BASE_BRANCH_NAME}" || {
                    echo ""
                    echo "[ERROR] Cannot create target branch from base branch '${BASE_BRANCH_NAME}' as it does not exist in repo '${REPO}'"
                    exit 1 ;
		}
		echo ""
		echo "[INFO] Creating target branch '${TARGET_BRANCH_NAME}' from base branch '${BASE_BRANCH_NAME}'"
		echo ""
		git checkout -b "${TARGET_BRANCH_NAME}"
            fi ;
	}

	git submodule init ${BUMP_REPO} || : # do not fail here - ${BUMP_REPO} might be set to an invalid ref
	git submodule update ${BUMP_REPO} || : # do not fail here - ${BUMP_REPO} might be set to an invalid ref
	cd ${BUMP_REPO}
	git checkout "${TARGET_BRANCH_NAME}"
	cd ..
	git add ${BUMP_REPO}
	git -c user.name="${USER_NAME}" -c user.email="${USER_EMAIL}" commit -m "Update ${BUMP_REPO} to origin/${TARGET_BRANCH_NAME}" || echo "already on origin/${TARGET_BRANCH_NAME}"
	git push origin "${TARGET_BRANCH_NAME}"

	echo ""
	echo "[OK] Repo '${REPO}' done!"
	cd ..
    done

    rm -rf "${WORK_DIR}" || echo "Warning: cannot remove the tmp working directory: ${WORK_DIR}"
}
