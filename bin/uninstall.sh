#!/bin/bash

# Uninstall katana processes

# Get the project directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && cd .. && pwd )"

# Stop all the containers and remove the db
bash ${DIR}/bin/stop.sh -c

# Remove the docker images
docker rmi -f $(docker images | grep katana | awk '{print $3}') &> /dev/null

# Remove katana commands
sudo rm /usr/local/bin/katana || true
