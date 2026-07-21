
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
bash bin/deploy.sh --bootstrap-config /path/to/bootstrap.yaml [other options]
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
- __[--bootstrap-config FILE] :__ Run the required Time-0 infrastructure reconciliation.
- __[--skip-bootstrap] :__ Skip reconciliation only for an already-configured installation.
- __[-h | --help] :__ Print help message and quit
## Logs

In order to get the logs of the katana-mngr and katana-nbi modules run:
```bash
katana logs [-l | --limit N]
```

For frontend slice observability, the NBI also exposes slice-specific monitoring
and log summary endpoints:

```bash
GET /api/slice/observability
GET /api/slice/<SLICE_ID>/observability
GET /api/slice/<SLICE_ID>/monitoring
GET /api/slice/<SLICE_ID>/monitoring/summary
GET /api/slice/<SLICE_ID>/monitoring/range?metric=<METRIC>&start=<UNIX>&end=<UNIX>&step=30s
GET /api/slice/<SLICE_ID>/alerts
GET /api/slice/<SLICE_ID>/logs?limit=100
```

`/monitoring` returns Grafana dashboard metadata and Prometheus queries/results
when slice monitoring is configured. `/monitoring/summary` returns
frontend-ready current values for slice, network-service, WIM, and VM metrics.
`/monitoring/range` returns Prometheus range data for one metric key returned by
the summary response. `/alerts` returns stored Alertmanager events for the
slice. `/logs` returns stored slice lifecycle events, alert events, runtime
errors, and best-effort matching NBI `katana.log` lines. Set
`KATANA_PUBLIC_GRAFANA_URL` or `KATANA_PUBLIC_PROMETHEUS_URL` if the frontend
should link to externally routed monitoring URLs instead of the default host
ports.

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

### Time-0 infrastructure bootstrap

NFVOs and OpenStack VIMs are installation configuration, not slice input. Copy
`templates/example_config_files/bootstrap`, replace the example credentials,
and deploy with the versioned manifest:

```bash
bash bin/deploy.sh --bootstrap-config /path/to/bootstrap/bootstrap.yaml
```

The one-shot job validates OSM and OpenStack, creates or adopts the configured
OSM VIM accounts, stores their NFVO-VIM links, and exits. Rerunning the same
manifest is safe and never deletes entries omitted from the file. Existing
configured installations may explicitly use `--skip-bootstrap` during upgrade.

The same reconciliation can be run later with:

```bash
katana bootstrap -f /path/to/bootstrap/bootstrap.yaml
```

Credential paths are relative to the manifest. Keep the credential files out of
source control. OpenStack credentials use the standard `clouds.yaml` format.
When a custom CA is configured, rerun the CLI with a manifest from the same
directory mounted during deployment so the NBI and manager can resolve it.

### Adding network function to Katana
```bash
sudo katana function add -f function.json
```
The network function JSON can retain its legacy `ns_list` metadata for mapping.
For Time-0 slices it does not trigger deployment; the slice
`service_descriptor.ns_list` below is the authoritative deployment list.

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

Every network service must select the registered NFVO and VIM explicitly.
Katana resolves the persistent OSM account from the bootstrapped link; callers
must not provide credentials or an `osm-vim-account-id` in slice YAML:

```yaml
service_descriptor:
  ns_list:
    - nsd-id: <existing OSM NSD ID>
      ns-name: <new NS instance name>
      nfvo-id: <registered Katana NFVO ID>
      target: <registered Katana OpenStack infrastructure ID>
      placement: core
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
url: "https://10.160.100.11:8006"
username: "root@pam"
password: "your_password"
```

The standalone Katana API registration uses the same minimum fields:

```bash
curl -X POST http://localhost:8000/api/proxmox/cluster \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://10.160.100.11:8006",
    "username": "root@pam",
    "password": "your_password"
  }'
```

Registration stores only the Proxmox connection details. It does not require a node or cluster/datacenter name. Katana reads the Proxmox cluster/datacenter name from the Proxmox API, so a cluster named `Antares` is returned by the backend and the user clicks it instead of typing it.

Example registration response shape:

```json
{
  "cluster_id": "saved-katana-id",
  "cluster_name": "Antares",
  "datacenters": [
    {
      "id": "cluster",
      "name": "Antares",
      "node_count": 3
    }
  ],
  "nodes": [],
  "servers": []
}
```

After the user clicks a datacenter, call `/api/proxmox/connect` with the selected `datacenter_id` or `datacenter_name` to return the nodes and servers for that selection.

If the same `url` is registered again, Katana validates the submitted credentials, refreshes the saved registration, and returns the existing `cluster_id` instead of a duplicate error. To log out/remove a saved Proxmox registration, call `DELETE /api/proxmox/cluster/<cluster_id>`.

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

Standalone-compatible Katana API endpoint:

```bash
curl -X POST http://localhost:8000/api/proxmox/provision \
  -H "Content-Type: application/json" \
  -d '{
    "name": "MyCluster",
    "url": "https://10.0.0.10:8006",
    "verify_ssl": false,
    "username": "root@pam",
    "password": "change-me",
    "node": "pve-node-01",
    "vms": [
      {
        "name": "katana-vm-1",
        "template": 9000,
        "cpu": 4,
        "ram": 4096,
        "storage_type": "local-lvm",
        "disk_size": 20,
        "bridges": [
          {"name": "vmbr0", "type": "management"}
        ]
      }
    ]
  }'
```

`template` is optional for this endpoint. If present, Katana clones that Proxmox template; if omitted or set to `null`, Katana creates a fresh VM with an empty disk on the selected storage and attaches the selected ISO image as a CD-ROM. Fresh VM creation requires `iso_image`. `storage_type` may be a plain Proxmox storage ID like `local-lvm` or a legacy value like `fast:vm`; Katana uses the storage ID before `:` when calling Proxmox. The same workflow is also available at `/api/proxmox/deploy`.

Fresh VMs default to `boot=order=<bootdisk>;ide2`, so Proxmox tries the hard disk first and falls back to the attached ISO/CD-ROM if the disk is still empty. During provisioning, Katana persists that boot order on the VM config before it sends the start request, so the UI can continue using a single deploy call.

ISO lists are included in `POST /api/proxmox/overview` and `POST /api/proxmox/servers` under each server `storage_options[].iso_images`, so the UI can load servers, storage, capacity, and ISO choices in one response. The UI should use the returned `volid` as `iso_image`, for example:

```json
{
  "volid": "local:iso/ubuntu-22.04-live-server-amd64.iso",
  "name": "ubuntu-22.04-live-server-amd64.iso",
  "storage": "local"
}
```

Fresh VM example without a template:

```bash
curl -X POST http://localhost:8000/api/proxmox/provision \
  -H "Content-Type: application/json" \
  -d '{
    "cluster_name": "MyCluster",
    "vms": [
      {
        "name": "katana-fresh-vm-1",
        "cpu": 2,
        "ram": 2048,
        "storage_type": "local-lvm",
        "disk_size": 20,
        "iso_image": "local:iso/ubuntu-22.04-live-server-amd64.iso",
        "start": false,
        "bridges": [
          {"name": "vmbr0", "type": "management"}
        ]
      }
    ]
  }'
```

For UI integration:

1. Register with `POST /api/proxmox/cluster` using only `url`, `username`, and `password`.
2. Show `datacenters[]`; the display label is `datacenters[].name`, for example `Antares`.
3. When the user clicks one, call `POST /api/proxmox/connect` with `cluster_id` and either `datacenter_id` or `datacenter_name`.
4. Show the returned `nodes` and `servers`, then let the user choose a server/node, storage, and VM options.
5. For fresh VM creation, require the user to choose one ISO `volid` from the selected storage's `iso_images`.
6. Call `POST /api/proxmox/provision` with `cluster_id`, selected `node`, and `vms`.
7. Use `template: <vmid>` for template clone deployments; omit `template` and include `iso_image` for fresh VM deployments.
8. After deployment, refresh inventory with `POST /api/proxmox/list-vms?node=<node>` or `POST /api/proxmox/overview`.

Datacenter click example:

```bash
curl -X POST http://localhost:8000/api/proxmox/connect \
  -H "Content-Type: application/json" \
  -d '{
    "cluster_id": "saved-katana-id",
    "datacenter_id": "cluster"
  }'
```

The deployment request waits for Proxmox clone/create/start tasks to finish. UI clients should use a long request timeout and show progress/loading while the request is in flight.

Deployment responses include VM IP information when Proxmox guest-agent reports it:

```json
{
  "cluster": "MyCluster",
  "node": "pve-node-01",
  "vm_count": 1,
  "results": [
    {
      "name": "katana-vm-1",
      "vmid": 123,
      "status": "created",
      "primary_ip": "10.160.101.55",
      "ip_addresses": ["10.160.101.55"],
      "ip_status": "ready",
      "network_interfaces": [
        {"name": "eth0", "ipv4": ["10.160.101.55"]}
      ]
    }
  ]
}
```

`ip_status` can be `ready`, `pending`, `not_started`, or `skipped`. For `ready`, show `primary_ip`. For `pending`, show the VM as deployed and display IP pending; the UI can refresh inventory later. Guest-agent IP detection is disabled by default because it requires the VM/template to be running with QEMU guest agent installed and enabled. Set `wait_for_ip: true` per VM only when guest-agent support is available. `ip_wait_timeout` and `ip_poll_interval` can tune this behavior.

The UI can also poll Proxmox for the VM IP after deployment:

```bash
curl -X POST http://localhost:8000/api/proxmox/vm-ip \
  -H "Content-Type: application/json" \
  -d '{
    "cluster_name": "MyCluster",
    "node": "pve-node-01",
    "vmid": 123
  }'
```

This endpoint reads IP information from Proxmox guest-agent data. The frontend should use the `vmid` returned by `/api/proxmox/provision`, then poll `/api/proxmox/vm-ip` until `ip_status` is `ready` or until its own timeout is reached.

To configure boot order first and start later, use two sequential requests:

```bash
curl -X POST http://localhost:8000/api/proxmox/vm-config \
  -H "Content-Type: application/json" \
  -d '{
    "cluster_name": "MyCluster",
    "node": "pve-node-01",
    "vmid": 123,
    "boot": "order=scsi0;ide2",
    "bootdisk": "scsi0",
    "onboot": 1
  }'
```

```bash
curl -X POST http://localhost:8000/api/proxmox/vm-start \
  -H "Content-Type: application/json" \
  -d '{
    "cluster_name": "MyCluster",
    "node": "pve-node-01",
    "vmid": 123
  }'
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
