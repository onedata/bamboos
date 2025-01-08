#!/usr/bin/env python3

"""Runs common tests in erlang using one-env.

The output is put into 'test_distributed/logs'. The (init|end)_per_suite
"testcases" are removed from the surefire.xml output.

All paths used are relative to script's path, not to the running user's CWD.
Run the script with -h flag to learn about script's running options.
"""

__author__ = "Michal Stanisz"
__copyright__ = "Copyright (C) 2020-2023 ACK CYFRONET AGH"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"


import glob
import os
import re
import sys

import ct_utils
from environment import docker, dockers_config
from environment.common import HOST_STORAGE_PATH, remove_dockers_and_volumes

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "bamboos/docker"))

COVER_SPEC = "cover.spec"
COVER_TMP_SPEC = "cover_tmp.spec"


def main():
    args = ct_utils.parse_args()
    args = configure_cover(args)

    dockers_config.ensure_image(args, "image", "worker")
    remove_dockers_and_volumes()

    return_code = run_tests(args)

    if return_code != 0 and not ct_utils.any_test_skipped(
        os.path.join(SCRIPT_DIR, "test_distributed/logs/*/surefire.xml")
    ):
        return_code = 0

    sys.exit(return_code)


def configure_cover(args):
    if cover_override := os.environ.get("bamboo_coverOptionOverride"):
        print("----------------------------------------------------")

        if cover_override == "true":
            print(
                "NOTE: overriding cover option to 'true' according to "
                "${bamboo_coverOptionOverride} ENV variable"
            )
            args.cover = True

        elif cover_override == "false":
            print(
                "NOTE: overriding cover option to 'false' according to "
                "${bamboo_coverOptionOverride} ENV variable"
            )
            args.cover = False

        elif cover_override == "develop_only":
            if os.environ.get("bamboo_planRepository_branchName") == "develop":
                print(
                    "NOTE: overriding cover option to 'true' for branch 'develop' "
                    "according to ${bamboo_coverOptionOverride} ENV variable"
                )
                args.cover = True
            else:
                print(
                    "NOTE: overriding cover option to 'false' for branch other than "
                    "'develop' according to ${bamboo_coverOptionOverride} ENV variable"
                )
                args.cover = False

        else:
            print(
                "WARNING: ignoring bad value for ${bamboo_coverOptionOverride} "
                f"ENV variable - '{cover_override}'"
            )

        print("----------------------------------------------------")
        sys.stdout.flush()

    if args.cover:
        print("----------------------------------------------------")
        print(
            "Cover is enabled, the tests will take longer to run due to setup and later analysis."
        )
        print("----------------------------------------------------")
        sys.stdout.flush()

        prepare_cover()

    return args


def prepare_cover():
    excl_mods = glob.glob(os.path.join(SCRIPT_DIR, "test_distributed", "*.erl"))
    excl_mods = [os.path.basename(item)[:-4] for item in excl_mods]
    cover_template = os.path.join(SCRIPT_DIR, "test_distributed", COVER_SPEC)
    new_cover = os.path.join(SCRIPT_DIR, "test_distributed", COVER_TMP_SPEC)

    incl_dirs = []
    with open(cover_template, "r") as template, open(new_cover, "w") as cover:
        for line in template:
            if "incl_dirs_r" in line:
                dirs_string = re.search(r"\[(.*?)\]", line).group(1)
                incl_dirs = [
                    os.path.join(SCRIPT_DIR, d[1:]) for d in dirs_string.split(", ")
                ]
            elif "excl_mods" in line:
                modules_string = re.search(r"\[(.*?)\]", line).group(1)
                excl_mods.extend([d.strip('"') for d in modules_string.split(", ")])
            else:
                print(line, file=cover)

        print('{{incl_dirs_r, ["{0}]}}.'.format(', "'.join(incl_dirs)), file=cover)
        print("{{excl_mods, [{0}]}}.".format(", ".join(excl_mods)), file=cover)


def run_tests(args):
    ct_cmd = prepare_ct_command(args)
    ct_env = ct_utils.prepare_ct_environment(args)

    return docker.run(
        tty=True,
        rm=True,
        interactive=True,
        workdir=os.path.join(SCRIPT_DIR, "test_distributed"),
        volumes=ct_utils.get_docker_volumes(),
        reflect=[
            (args.path_to_sources, "rw"),
            (SCRIPT_DIR, "rw"),
            ("/var/run/docker.sock", "rw"),
            (HOST_STORAGE_PATH, "rw"),
            ("/etc/passwd", "ro"),
        ],
        name="testmaster",
        hostname="testmaster.test",
        image=args.image,
        command=ct_utils.get_docker_command(ct_cmd, ct_env),
    )


def prepare_ct_command(args):
    ct_command = [
        "ct_run",
        "-abort_if_missing_suites",
        "-dir", ".",
        "-logdir", "./logs/",
        "-ct_hooks",
        "cth_surefire", '[{path, "surefire.xml"}]',
        "and", "cth_logger",
        "and", "cth_onenv_up",
        "and", "cth_mock",
        "and", "cth_posthook",
        "-noshell",
        "-name", "testmaster@testmaster",
        "-hidden",
        "-include", "./include", "../include", "../_build/default/lib",
    ]

    code_paths = ["-pa"]

    code_paths.extend(
        glob.glob(os.path.join(SCRIPT_DIR, "_build/default/lib", "*", "ebin"))
    )
    ct_command.extend(code_paths)

    if args.suites:
        ct_command.append("-suite")
        ct_command.extend([locate_suite(s) for s in args.suites])

    if args.groups:
        ct_command.append("-group")
        ct_command.extend(args.groups)

    if args.cases:
        ct_command.append("-case")
        ct_command.extend(args.cases)

    if args.cover:
        ct_command.extend(["-cover", COVER_TMP_SPEC])

    config_path = os.path.abspath("bamboos/env_configurator/test.config")
    ct_command.extend(["-erl_args", "-enable-feature", "maybe_expr", "-config", config_path])

    return ct_command


def locate_suite(name):
    if "/" in name:
        print(
            "NOTE: it is no longer required to provide full path(s) to the "
            "suite(s) you wish to run. It is enough to provide the suite name "
            "(without the '_test_SUITE' suffix)."
        )
        name = os.path.basename(name)

    if "_test_SUITE" not in name:
        name += "_test_SUITE"

    if ".erl" not in name:
        name += ".erl"

    return ct_utils.find_suite_file(name)


if __name__ == "__main__":
    main()
