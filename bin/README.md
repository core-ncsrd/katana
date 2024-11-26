# Binary Files and Scripts

This directory contains scripts that automate the deployment process of Katana Slice Manager

- __build.sh:__ Build the Docker Images based on the specified Docker registry, repository, user, and release tag. Additionally, the Katana CLI tool will be installed.
- __deploy.sh:__ Deploy the Katana services
- __stop.sh:__ Stop all the running Katana services
- __uninstall.sh:__ Remove the Docker resources and installed tool related to Katana
- __slice_creation_time:__ Python based tool that can be used for measuring the slice creation time. It can be installed using pip. More details in the tools [README file](slice_creation_time/README.md)
