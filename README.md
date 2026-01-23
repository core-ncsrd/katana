
![Katana Logo](./templates/images/katana-logo.svg)


## Contributing

Code Contributions

Original Contributors
- themisAnagno (Themis Anagostopoulos)
- tgogos (Anastasios Gogos)
- xilouris (George Xilouris)
- santojim (Jim Santorineos)

  <br>**Current Maintainer/Developer**

- TheReaperGR (Leonis Panagiotis)





# KATANA Slice Manager

Katana Slice Manager is a centralized software component that provides an interface for creating, modifying, monitoring, and deleting slices. Through the North Bound Interface (NBI), the Slice Manager receives the Network Slice Template (NEST) for creating network slices and provides the API for managing and monitoring them. Through the South Bound Interface (SBI), it communicates with the Network Sub-Slice Manager components of the Management Layer, namely the Virtual Infrastructure Manager (VIM), the NFV Orchestrator (NFVO), the Element Management System (EMS), and the WAN Infrastructure Management (WIM).

Katana Slice Manager is based on a highly modular architecture, built as a mesh of microservices, each of which is running on a docker container. The key advantages of this architectural approach are that it offers simplicity in building and maintaining applications, flexibility and scalability, while the containerized approach makes the applications independent of the underlying system.




## Features

- Start, Stop, Inspect End-to-End Network Slices
- OpenAPIs
- Modular architecture for supporting different infrastructure technologies
- Integrated CLI tool
- Slice Day-2 operations **[Enhanced]**
- Prometheus and Grafana Monitoring modules **[Enhanced]**
- Integrated Policy Engine System
- Slice Deployment and Configuration measurements
- K8s/K3s support **[NEW]**
- **PQC (Post-Quantum Cryptography) with Besu Blockchain** **[NEW]**
- **Proxmox VM Management Integration** **[NEW]**
- **5G Stack Deployment (Open5GS/UERANSIM)** **[NEW]**


## Installation


To Install KATANA you must download the repo extract it then run 
go inside the project and run:

```bash
  sudo ./bin/build.sh
```
## Deployment

Deploy katana Slice Manager service. The script will attempt to pull the defined Docker tag from the defined Docker registry/repository. Otherwise, it will build the images using the ":test" tag.

``` bash
bash bin/deploy.sh [-p | --publish] [-r | --release <RELEASE_NUMBER>] [--docker_reg <REMOTE_DOCKER_REGISTRY>] [--docker_repo <DOCKER_REPOSITORY>] [--docker_reg_user <REGISTRY_USER>] [--docker_reg_passwd <REGISTRY_PASSWORD>] [-m | --monitoring] [--no-build] [--apex] [-h | --help]
```

Options:

- __[-p | --publish] :__ Expose Kafka end Swagger-ui using katana public IP
- __[-r | --release <RELEASE_NUMBER>] :__ Define the release that will match the Docker Tag of Katana Docker images (Default: :test).
- __[--docker_reg <REMOTE_DOCKER_REGISTRY>] :__ Define the remote Docker registry. If no docker registry is specified, Katana will try to use the public Docker hub
- __[--docker_repo <DOCKER_REPOSITORY>] :__ Define the Docker repository
- __[--docker_reg_user <REGISTRY_USER>] :__ Define the user of the remote Docker registry
- __[--docker_reg_passwd <REGISTRY_PASSWORD>] :__ Define the password for the user of the remote Docker registry
- __[-m | --monitoring] :__ Start Katana Slice Manager Slice Monitoring module
- __[--no_build] :__ Try to download Docker images, but do not build them
- __[--apex] :__ Initiate the APEX Policy Engine
- __[-h | --help] :__ Print help message and quit
## Logs

In order to get the logs of the katana-mngr and katana-nbi modules run:
```bash
katana logs [-l | --limit N]
```

## Stop
Stop Katana Slice Manager:

```bash 
bin/stop.sh [-c | --clear] [-h | --help]
```

- **[-c | --clear]** : Remove the container volumes
- **[-h | --help]** : Print help message and quit

## Uninstall
To Uninstall Katana Slice Manager run the following:

```bash
.bin/uninstall.sh
```
## Usage/Examples

**We assume that an OSM 16 and a K8s/MicroK8s cluster or Openstack have been installed and configured properly and that the user has already uploaded an nsd/vnfd to osm**

### Registering NVFO to Katana
```bash
sudo katana nfvo add -f osm.json
```
with this command we register our osm the format of the json is the following

```json
{
  "id": "<Give id>",
  "name": "<Give a name>",
  "nfvoip": "nbi.<ip of OSM>.nip.io",
  "nfvousername": "admin",
  "nfvopassword": "admin",
  "tenantname": "admin",
  "type": "OSM",
  "version": "",
  "description": "string",
  "config": [
    {
      "id": "0",
      "nfvousername": "admin",
      "nfvopassword": "admin",
      "nfvoip": "nbi.<ip of OSM>.nip.io",
      "tenantname": "admin"
    }
  ]
}
```
### Registering location to Katana
```bash
sudo katana location add -f location.json
```
with this command we register the location of a vim the format of the json is the following

```json
{

"id": "group0_edge",

"description": "Group 0 Edge location"

}
```
### Registering a VIM to Katana
```bash
sudo katana vim add -f vim.json
```

Running this will register a vim to katana json format is below

```json
{
  "id": "vim_core2",
  "name": "vim_Core2",
  "auth_url": "http://<IP of the openstack>:5000/v3/",
  "username": "admin",
  "password": "<password given by openstack>",
  "admin_project_name": "admin",
  "location": "<Should be the same as the location id>",
  "type": "openstack",
  "version": "2024.1/stable",
  "description": "Group 0 VIM",
  "infrastructure_monitoring": "http://<IP of the openstack>:9093/metrics",
  "config": {
    "security_groups": "TBA"
  }
}
```

### Adding network function to Katana
```bash
sudo katana function add -f function.json
```
the network function json should look like this

```json
{
  "id": "group0_demo5GCore",
  "name": "group0_demo5GCore",
  "gen": 5,
  "func": 0,
  "shared": {
    "availability": false
  },
  "type": 0,
  "location": "<Location ID of where this should be registered to>",
  "pnf_list": [],
  "ns_list": [
    {
      "nsd-id": "<id of the NSD file that has been uploaded to OSM>",
      "ns-name": "<Name of the NSD file that has been uploaded to OSM>",
      "placement": 0,
      "optional": false
    }
  ]
}
```

### Adding a slice to Katana
```bash
sudo katana slice add -f slice.json
```

the json for the slice should be like this
```json
{
  "base_slice_descriptor": {
    "base_slice_des_id": "group0_demo_slice",
    "coverage": [
      "group0_edge"
    ],
    "delay_tolerance": true,
    "network_DL_throughput": {
      "guaranteed": 1500000
    },
    "ue_DL_throughput": {
      "guaranteed": 1500000
    },
    "network_UL_throughput": {
      "guaranteed": 50000
    },
    "ue_UL_throughput": {
      "guaranteed": 60000
    },
    "mtu": 1500
  },
  "service_descriptor": {
    "ns_list": [
      {
        "nsd-id": "<ID of the NSD that has been uploaded to OSM>",
        "ns-name": "Name of the NSD that has been uploaded to OSM",
        "placement": 0,
        "optional": false
      }
    ]
  }
}
```
## K8s/MicroK8s Configuration
**We assume that a there is already a helm chart uploaded somewhere for osm to deploy and the user has uploaded the appropriate nsd/knf to OSM**

### Registering NVFO
```bash
sudo katana nfvo add -f osm.json
```
with this command we register our osm. The format of the json is the following

```json
{
  "id": "<Give id>",
  "name": "<Give a name>",
  "nfvoip": "nbi.<ip of OSM>.nip.io",
  "nfvousername": "admin",
  "nfvopassword": "admin",
  "tenantname": "admin",
  "type": "OSM",
  "version": "",
  "description": "string",
  "config": [
    {
      "id": "0",
      "nfvousername": "admin",
      "nfvopassword": "admin",
      "nfvoip": "nbi.<ip of OSM>.nip.io",
      "tenantname": "admin"
    }
  ]
}
```
### Uploading Cluster Credentials
**The user needs to get the kubernets config from the cluster which contains the ip and the hash for the whole cluster in order to be parsed to katana**
```bash
sudo katana k8s uploadcreds -f creds.yaml
```
### Registering Cluster to Katana

```bash
sudo katana k8s add -f k8s.json
```
The json for registering kubernetes has the following

```json
{
  "schema_version": "1.0",
  "credentials": "creds.yaml",
  "schema_type": "k8scluster",
  "name": "Microk8sCluster3",
  "description": "Isolated K8s cluster in mylocation",
  "vim_account": "<Vim id of a dummy vim registerd by the OSM>",
  "nfvo_ip": "nbi.<OSM IP>.nip.io",
  "nfvo_username": "admin",
  "nfvo_password": "admin",
  "k8s_version": "v1.30.7",
  "nets": {
    "k8s_net1": null
  },
  "namespace": "default",
  "deployment_methods": {
    "juju-bundle": true,
    "helm-chart-v3": true
  }
}
```

### Deploying a Service to the Cluster
```bash
sudo katana k8s deploy -f service.json
```
```json
{

"nfvo_id": "<ID that katana give back after registerning the OSM>",

"nsdId": "<id of the NSD>",

"nsName": "<name of the NSD>",

"nsDescription": "default description",

"vimAccountId": "<VIM id of the new vim that will be created after registering the k8s cluster>"

}
```
### Migrating a pod
```bash
sudo katana k8s migration -f migration.json
```
```json
{
  "pod_prefix": "open5gs-2-2-8-tgz-0094188170-mec-service",
  "target_node": "<name of the worker that we want to migrate the pod to>",
  "namespace": "<Namespace of the pods we want to migrate>",
  "deployment": "<Extact Name of the pod>",
  "config": "creds/<Extact name of the credential file we uploaded for the cluster we registerd>"
}
```

---

## PQC (Post-Quantum Cryptography) Deployment

Katana supports deploying slices with Post-Quantum Cryptography enabled via Hyperledger Besu blockchain. The `--pqc` flag triggers an Ansible controller to deploy Besu nodes before slice creation.

### Prerequisites for PQC
- Ansible Controller server running at port 5000
- Besu ansible playbooks configured at `/home/localadmin/besu-ansible`
- Network connectivity to the Ansible controller

### Creating a Slice with PQC
```bash
# Standard slice creation
sudo katana slice add -f slice.yaml

# With PQC/Besu blockchain deployment
sudo katana slice add --pqc -f slice.yaml
# You will be prompted: "Enter the Ansible controller IP address [10.160.101.122]:"
```

When using `--pqc`:
1. CLI prompts for Ansible controller IP (default: 10.160.101.122)
2. Sends request to `http://<ANSIBLE_IP>:5000/run_playbook`
3. Ansible executes `start_nodes.yml` to deploy Besu blockchain
4. On success, proceeds with slice creation

---

## Proxmox VM Management

Katana can create and manage VMs on Proxmox clusters using the `--prox` flag or dedicated Proxmox CLI commands.

### Registering a Proxmox Cluster
```bash
sudo katana proxmox add -f proxmox_cluster.yaml
```

Example `proxmox_cluster.yaml`:
```yaml
name: "MyCluster"
url: "https://10.160.100.11:8006"
username: "root@pam"
password: "your_password"
node: "proxmox-node-01"
```

### Creating VMs from YAML
```bash
# Create VMs only
sudo katana slice add --prox proxmox_vms.yaml

# Create VMs then create slice
sudo katana slice add --prox proxmox_vms.yaml -f slice.yaml

# Full deployment: Besu + VMs + Slice
sudo katana slice add --pqc --prox proxmox_vms.yaml -f slice.yaml
```

Example `proxmox_vms.yaml`:
```yaml
cluster_name: "MyCluster"
vms:
  - name: "katana-vm-1"
    template: "101"
    cpu: 4
    ram: 4096
    storage_type: "local-lvm"
    disk_size: 20
    bridges:
      - name: "vmbr0"
        type: "management"
      - name: "vmbr1"
        type: "custom"
        ip: "192.168.10.10"
        netmask: "255.255.255.0"
        gateway: "192.168.10.1"
```

### Proxmox CLI Commands
```bash
# List registered clusters
sudo katana proxmox ls

# Remove a cluster
sudo katana proxmox rm <CLUSTER_ID>

# List all VMs
sudo katana proxmox vms

# Create VMs directly
sudo katana proxmox vm-add -f proxmox_vms.yaml
```

---

## Quick Reference

| Deployment Type | Command |
|-----------------|---------|
| Standard slice | `katana slice add -f slice.yaml` |
| PQC-enabled slice | `katana slice add --pqc -f slice.yaml` |
| Proxmox VMs only | `katana slice add --prox vms.yaml` |
| VMs + Slice | `katana slice add --prox vms.yaml -f slice.yaml` |


For detailed deployment instructions, see [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md).
