#!/bin/bash

# Check for help option
if [[ " $* " =~ " -h " ]] || [[ " $* " =~ " --help " ]];
then
    printf "Usage:\n\tbuild.sh [-r | --release <RELEASE_NUMBER>] [--docker_reg <REMOTE_DOCKER_REGISTRY>] [--docker_repo <DOCKER_REPOSITORY>]\n\t\t [--docker_reg_user <REGISTRY_USER>] [--docker_reg_passwd <REGISTRY_PASSWORD>] [--push] [--dev] [-h | --help]\nOptions:
\t[-r | --release <RELEASE_NUMBER>] : Define the release that will match the Docker Tag of Katana Docker images (Default: :test).
\t[--docker_reg <REMOTE_DOCKER_REGISTRY>] : Define the remote Docker registry. If no docker registry is specified, Katana will try to use the public Docker hub
\t[--docker_repo <DOCKER_REPOSITORY>] : Define the Docker repository
\t[--docker_reg_user <REGISTRY_USER>] : Define the user of the remote Docker registry
\t[--docker_reg_passwd <REGISTRY_PASSWORD>] : Define the password for the user of the remote Docker registry
\t[--push] : Push the images to the remote Docker registry
\t[--dev] : Create a dev workspace for development purposes
\t[-h | --help] : Print this message and exit\n"
    exit 0
fi

# Get the project directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && cd .. && pwd )"

# Check if the user and release fare defined
while [[ $# -gt 0 ]]
do
    key=$1

    case $key in
    -r | --release)
        export DOCKER_TAG="$2"
        shift
        shift
        ;;
    --docker_reg)
        export DOCKER_REG="$2/"
        shift
        shift
        ;;
    --docker_repo)
        export DOCKER_REPO="$2/"
        shift
        shift
        ;;
    --docker_reg_user)
        export DOCKER_REG_USER="$2"
        shift
        shift
        ;;
    --docker_reg_passwd)
        export DOCKER_REG_PASSWD="$2"
        shift
        shift
        ;;
    --push)
        PUSH_IMAGE=true
        shift
        ;;
    --dev)
        # *** Install development environment ***
        echo "Installing development environment"
        # Copy hard links of the shared utils in katana-mngr and katana-nbi
        read -r -p "Any dev/dev_shared_utils will be lost. Continue? (Y/n) > " ans
        if [[ $ans =~ ^n.* ]];
        then
            exit 9999
        fi
        echo "Creating dev/dev_shared_utils. They are hard-linked to both common files in katana-mngr and katana-nbi directories"
        mkdir -p "${DIR}/dev/dev_config_files" &> /dev/null && echo "Created dev folder"
        cp -r "${DIR}/templates/example_config_files/"* "${DIR}/dev/dev_config_files/"
        echo "Creating dev/dev_config_files. They can be used for actual testing. They won't be pushed to remote repository"
        rm -rf "${DIR}/katana-nbi/katana/shared_utils" &> /dev/null
        rm -rf "${DIR}/dev/dev_shared_utils" &> /dev/null
        cp -al "${DIR}/katana-mngr/katana/shared_utils" dev/dev_shared_utils &> /dev/null
        cp -al "${DIR}/katana-mngr/katana/shared_utils" katana-nbi/katana/ &> /dev/null
        exit
        ;;
    *)
        printf "Wrong option %s\nUse the --help option\n--------\n" "${key}"
        exit 1
        ;;
    esac
done

# Check if the Docker user and passwd are set. If yes, login to docker registry
if [[ ! -z ${DOCKER_REG_USER+x} && ! -z ${DOCKER_REG_PASSWD+x} ]]; then
        docker login -u ${DOCKER_REG_USER} -p ${DOCKER_REG_PASSWD} ${DOCKER_REG}
fi

# Check if the docker tag is set. Otherwise set it to test
if [[ -z ${DOCKER_TAG+x} ]]; then
        export DOCKER_TAG="test"
fi

# Build the images
printf "********************************\n"
printf "**** Building Katana images ****\n"
printf "********************************\n"
docker-compose -f ${DIR}/docker-compose.yaml build
if [[ "${PUSH_IMAGE}" == true ]]; then
    printf "*************************\n"
    printf "**** Pushing Images  ****\n"
    printf "*************************\n"
    docker-compose -f ${DIR}/docker-compose.yaml push
fi

# Install the katana command
printf "***********************************\n"
printf "**** Installing Katana Command ****\n"
printf "***********************************\n"
command -v katana &> /dev/null || sudo cp ${DIR}/bin/katana /usr/local/bin/