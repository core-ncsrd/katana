#!/bin/bash

function build_katana_images {
    if [[ "${NO_BUILD}" != true ]]
    then
        docker compose -f "${DIR}/docker-compose.yaml" build
    else
        printf "ERROR: Could not pull Docker images and the --no_build flag is set\n"
        exit 1
    fi
}

containers="mongo zookeeper kafka katana-nbi katana-mngr katana-cli katana-swagger"
export KATANA_MONITORING=""
export APEX=""
BOOTSTRAP_CONFIG=""
SKIP_BOOTSTRAP=false

# Get the project directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && cd .. && pwd )"

# Check for help option
if [[ " $* " =~ " -h " ]] || [[ " $* " =~ " --help " ]];
then
     printf "Usage:\n\tdeploy.sh [-p | --publish] [-r | --release <RELEASE_NUMBER>] [--docker_reg <REMOTE_DOCKER_REGISTRY>] [--docker_repo <DOCKER_REPOSITORY>]\n\t\t  [--docker_reg_user <REGISTRY_USER>] [--docker_reg_passwd <REGISTRY_PASSWORD>] [-m | --monitoring] [--no_build] [--apex]\n\t\t  [--bootstrap-config <FILE> | --skip-bootstrap] [-h | --help]\nOptions:
\t[-p | --publish] : Expose Kafka end Swagger-ui using katana public IP
\t[-r | --release <RELEASE_NUMBER>] : Define the release that will match the Docker Tag of Katana Docker images
\t[--docker_reg <REMOTE_DOCKER_REGISTRY>] : Define the remote Docker registry. If no docker registry is specified, Katana will try to use the public Docker hub
\t[--docker_repo <DOCKER_REPOSITORY>] : Define the Docker repository
\t[--docker_reg_user <REGISTRY_USER>] : Define the user of the remote Docker registry
\t[--docker_reg_passwd <REGISTRY_PASSWORD>] : Define the password for the user of the remote Docker registry
\t[-m | --monitoring] : Start the monitoring module
\t[--no_build] : Try to download Docker images, but do not build them
\t[--apex] : Initiate the APEX Policy Engine
\t[--bootstrap-config <FILE>] : Reconcile Time-0 NFVO/VIM configuration before startup
\t[--skip-bootstrap] : Explicitly skip bootstrap for an existing installation
\t[-h | --help] : Print this message and quit\n"
        exit 0
fi

# Get the options
while [[ $# -gt 0 ]]
do
    key=$1

    case $key in
    -p | --publish)
        PUBLISH=true
        message="katana host public IP"
        ip_list=$(hostname -I 2> /dev/null)
        if (( $? == 0 ));
        then
            message="${message} (Available: $ip_list)"
        fi
        read -r -p "${message} >> " HOST_IP
        export "KATANA_HOST=${HOST_IP}"
        shift
    ;;
    -m | --monitoring)
        containers="${containers} katana-prometheus katana-grafana katana-nfv_mon katana-alertmanager"
        # Check if katana-grafana/.env file exists - If not create it
        if [ ! -f "${DIR}/katana-grafana/.env" ];
        then
        echo "GF_SECURITY_ADMIN_PASSWORD=admin" > "${DIR}/katana-grafana/.env"
        echo "GF_SECURITY_ADMIN_USER=admin" >> "${DIR}/katana-grafana/.env"
        fi
        export KATANA_MONITORING=True
        shift
    ;;
    -r | --release)
        export DOCKER_TAG=$2
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
    --no_build)
        export NO_BUILD=true
        shift
        ;;
    --apex)
        export APEX=true
        containers="${containers} katana-apex"
        shift
        ;;
    --bootstrap-config)
        if [[ -z "$2" ]]; then
            printf "ERROR: --bootstrap-config requires a file\n"
            exit 1
        fi
        BOOTSTRAP_CONFIG="$2"
        shift
        shift
        ;;
    --skip-bootstrap)
        SKIP_BOOTSTRAP=true
        shift
        ;;
    *)
        printf "Wrong option %s\n--------\n" "${key}"
        printf "Usage:\n\tdeploy.sh [-p | --publish] [-r | --release <RELEASE_NUMBER>] [--docker_reg <REMOTE_DOCKER_REGISTRY>] [--docker_repo <DOCKER_REPOSITORY>]\n\t\t  [--docker_reg_user <REGISTRY_USER>] [--docker_reg_passwd <REGISTRY_PASSWORD>] [-m | --monitoring] [--no_build] [--apex] [-h | --help]\nOptions:
\t[-p | --publish] : Expose Kafka end Swagger-ui using katana public IP
\t[-r | --release <RELEASE_NUMBER>] : Define the release that will match the Docker Tag of Katana Docker images (Default: :test)
\t[--docker_reg <REMOTE_DOCKER_REGISTRY>] : Define the remote Docker registry. If no docker registry is specified, Katana will try to use the public Docker hub
\t[--docker_repo <DOCKER_REPOSITORY>] : Define the Docker repository
\t[--docker_reg_user <REGISTRY_USER>] : Define the user of the remote Docker registry
\t[--docker_reg_passwd <REGISTRY_PASSWORD>] : Define the password for the user of the remote Docker registry
\t[-m | --monitoring] : Start the monitoring module
\t[--no_build] : Try to download Docker images, but do not build them
\t[--apex] : Initiate the APEX Policy Engine
\t[--bootstrap-config <FILE>] : Reconcile Time-0 NFVO/VIM configuration before startup
\t[--skip-bootstrap] : Explicitly skip bootstrap for an existing installation
\t[-h | --help] : Print this message and quit\n"
        exit 1
        ;;
    esac
done

if [[ -n "${BOOTSTRAP_CONFIG}" && "${SKIP_BOOTSTRAP}" == true ]]; then
    printf "ERROR: --bootstrap-config and --skip-bootstrap cannot be used together\n"
    exit 1
fi
if [[ -z "${BOOTSTRAP_CONFIG}" && "${SKIP_BOOTSTRAP}" != true ]]; then
    printf "ERROR: New deployments require --bootstrap-config <FILE>; use --skip-bootstrap only for an existing configured installation\n"
    exit 1
fi
if [[ -n "${BOOTSTRAP_CONFIG}" ]]; then
    if [[ ! -f "${BOOTSTRAP_CONFIG}" ]]; then
        printf "ERROR: Bootstrap manifest %s was not found\n" "${BOOTSTRAP_CONFIG}"
        exit 1
    fi
    KATANA_BOOTSTRAP_DIR="$(cd "$(dirname "${BOOTSTRAP_CONFIG}")" && pwd)"
    KATANA_BOOTSTRAP_MANIFEST="$(basename "${BOOTSTRAP_CONFIG}")"
    export KATANA_BOOTSTRAP_DIR
    export KATANA_BOOTSTRAP_MANIFEST
fi

# If Release Tag is set, try to download it. Otherwise set it to test and build the images
export DOCKER_TAG=${DOCKER_TAG:-test}
export DOCKER_REG=${DOCKER_REG:-""}
export DOCKER_REPO=${DOCKER_REPO:-""}
if [[ -z ${DOCKER_TAG_OVERRIDE+x} ]];
then
    build_katana_images
else
    # Check if the Docker user and passwd are set. If yes, login to docker registry
    if [[ ! -z ${DOCKER_REG_USER+x} && ! -z ${DOCKER_REG_PASSWD+x} ]]; then
        docker login -u ${DOCKER_REG_USER} -p ${DOCKER_REG_PASSWD} ${DOCKER_REG}
    fi
    docker compose -f "${DIR}/docker-compose.yaml" pull || build_katana_images
fi

# Install the command for the cli tool to /usr/local/bin/
command -v katana &> /dev/null || sudo cp "${DIR}/bin/katana" /usr/local/bin/

# Reconcile infrastructure before services can accept slice requests.
if [[ -n "${BOOTSTRAP_CONFIG}" ]]; then
    docker compose -f "${DIR}/docker-compose.yaml" --profile bootstrap run --rm katana-bootstrap || exit 1
fi

# Start the docker containers on the background
docker compose -f "${DIR}/docker-compose.yaml" up -d ${containers}

# Fix the Release number and Katana IP on swagger
docker exec katana-swagger sh /my_swagger/fixVersion.sh

if [[ "${PUBLISH}" == true ]];
then
    docker exec katana-swagger sh /my_swagger/fixIP.sh
fi
