# Scripts for copying artifacts to external storage

Use `push_artifact.py` and `pull_artifact.py` to copy bamboo artifacts to and from
external storage. Currently we use S3 bucket on `storage.cloud.cyfronet.pl` named
`bamboo-artifacts-2` to store the bamboo artifacts. It is reflected in the scripts
arguments in the bamboo plans/tasks.

## Setting up local credentials for S3

In order to push/pull artifacts to the bucket you need to place your S3 credentials
in `~/.aws/credential`. Example content of this file:
```
[default]
aws_access_key_id = my-access-key
aws_secret_access_key = my-secret-key
```

## Using with no credentials

There is a S3proxy server deployed to allow anonymous read only access
to the bucket which is accessible via our VPN. For more details about
the proxy server see <https://confluence.onedata.org/spaces/VFS/pages/55280270/proxy.devel.onedata.org>.
The `pull_artifact.py` script will use it if the file `~/.aws/credentials` is not found.
