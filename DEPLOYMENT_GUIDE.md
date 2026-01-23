# Katana Slice Manager - Complete Deployment Guide

## Table of Contents

1. [Introduction](#introduction)
2. [Architecture Overview](#architecture-overview)
3. [Prerequisites](#prerequisites)
4. [Standard Deployment (Without PQC)](#standard-deployment-without-pqc)
5. [PQC Deployment (With Besu Blockchain)](#pqc-deployment-with-besu-blockchain)
6. [Proxmox VM Deployment](#proxmox-vm-deployment)
7. [CLI Reference](#cli-reference)
8. [Configuration Files](#configuration-files)
9. [Troubleshooting](#troubleshooting)

---

## Introduction

Katana Slice Manager is a centralized software component for creating, modifying, monitoring, and deleting 5G network slices. This guide covers two deployment modes:

1. **Standard Deployment**: Traditional slice creation without blockchain security
2. **PQC Deployment**: Post-Quantum Cryptography enabled deployment using Hyperledger Besu blockchain, triggered via Ansible automation

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           KATANA SLICE MANAGER                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │ katana-cli  │───▶│ katana-nbi  │───▶│ katana-mngr │───▶│   MongoDB   │  │
│  │   (CLI)     │    │  (REST API) │    │  (Manager)  │    │  (Database) │  │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘  │
│         │                  │                  │                             │
│         │                  │                  │                             │
│         ▼                  ▼                  ▼                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                     │
│  │  --pqc flag │    │   Proxmox   │    │    Kafka    │                     │
│  │  (Ansible)  │    │     API     │    │  (Messaging)│                     │
│  └─────────────┘    └─────────────┘    └─────────────┘                     │
│         │                  │                                                │
│         ▼                  ▼                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    EXTERNAL INFRASTRUCTURE                          │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐              │   │
│  │  │  Ansible    │    │   Proxmox   │    │    NFVO     │              │   │
│  │  │ Controller  │    │   Cluster   │    │   (OSM)     │              │   │
│  │  │ (Besu)      │    │   (VMs)     │    │             │              │   │
│  │  └─────────────┘    └─────────────┘    └─────────────┘              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Components

| Component | Description | Port |
|-----------|-------------|------|
| **katana-nbi** | North Bound Interface - REST API server | 8000 |
| **katana-mngr** | Slice Manager - Handles slice lifecycle | Internal |
| **katana-cli** | Command Line Interface | N/A |
| **MongoDB** | Database for slice and configuration storage | 27017 |
| **Kafka** | Message broker for async operations | 9092 |
| **katana-swagger** | API documentation UI | 8001 |
| **katana-pqc-kpi** | PQC KPI monitoring service | Internal |
| **katana-prometheus** | Metrics collection | 9090 |
| **katana-grafana** | Monitoring dashboards | 3000 |

---

## Prerequisites

### System Requirements
- **Docker** version >= 18.09.6
- **Docker Compose** version >= 1.17.1
- **Linux** (Ubuntu 20.04+ recommended)
- At least 8GB RAM, 4 CPU cores

### For PQC Deployment (Additional)
- **Ansible Controller Server** running the Besu playbook API
- **Hyperledger Besu** blockchain nodes configured
- Network connectivity to the Ansible controller (default: port 5000)

### For Proxmox Deployment (Additional)
- **Proxmox VE** cluster with API access
- VM templates pre-configured
- Network bridges configured (vmbr0, vmbr1, etc.)

---

## Standard Deployment (Without PQC)

### Step 1: Build Katana Images

```bash
cd katana-updated
bash bin/build.sh
```

**Options:**
- `-r | --release <VERSION>` - Set Docker image tag (default: test)
- `--push` - Push images to remote registry
- `--dev` - Enable development mode

### Step 2: Deploy Katana Services

```bash
bash bin/deploy.sh
```

**Options:**
- `-p | --publish` - Expose services on public IP
- `-m | --monitoring` - Enable Prometheus/Grafana monitoring
- `--apex` - Enable APEX Policy Engine

### Step 3: Configure Infrastructure

#### Register NFVO (e.g., OSM)
```bash
katana nfvo add -f osm.json
```

Example `osm.json`:
```json
{
  "id": "osm1",
  "type": "osm",
  "url": "https://10.160.100.10:9999",
  "username": "admin",
  "password": "admin",
  "project": "admin"
}
```

#### Register VIM (Virtual Infrastructure Manager)
```bash
katana vim add -f vimCore.json
katana vim add -f vimEdge.json
```

Example `vimCore.json`:
```json
{
  "id": "vim_core",
  "type": "openstack",
  "url": "http://10.160.100.20:5000/v3",
  "username": "admin",
  "password": "secret",
  "project_name": "admin"
}
```

#### Register Location
```bash
katana location add -f templates/example_config_files/location/example_group0_edge.json
```

#### Register Functions
```bash
katana function add -f templates/example_config_files/Functions/example_demo5gcore.json
katana function add -f templates/example_config_files/Functions/example_demo5ggnb.json
```

### Step 4: Create a Slice

```bash
katana slice add -f basicSlice.yaml
```

Example `basicSlice.yaml`:
```yaml
base_slice_descriptor:
  base_slice_des_id: "minimal_slice"
  coverage:
    - "default_location"
  delay_tolerance: true
  network_DL_throughput:
    guaranteed: 100
    maximum: 500
  network_UL_throughput:
    guaranteed: 100
    maximum: 500
  isolation_level:
    isolation: 0
  number_of_connections: 5
  number_of_terminals: 5

service_descriptor:
  ns_list:
    - nfvo-id: "osm1"
      nsd-id: "demo_nsd"
      ns-name: "core_network_service"
      placement: 1
      vim-id: "vim_core"
```

### Step 5: Verify Slice

```bash
# List all slices
katana slice ls

# Inspect specific slice
katana slice inspect <SLICE_UUID>

# Check deployment time
katana slice deployment-time <SLICE_UUID>

# Check for errors
katana slice errors <SLICE_UUID>
```

---

## PQC Deployment (With Besu Blockchain)

The `--pqc` flag enables **Post-Quantum Cryptography** by deploying a Hyperledger Besu blockchain network before creating the slice. This adds a cryptographic layer for enhanced security.

### How Besu Blockchain Deployment Works

```
┌─────────────────────────────────────────────────────────────────┐
│                    PQC DEPLOYMENT FLOW                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. User runs: katana slice add --pqc -f slice.yaml            │
│                           │                                     │
│                           ▼                                     │
│  2. CLI prompts: "Enter Ansible controller IP [10.160.101.122]:"│
│                           │                                     │
│                           ▼                                     │
│  3. CLI sends POST to Ansible Controller:                       │
│     URL: http://<ANSIBLE_IP>:5000/run_playbook                 │
│     Payload: {                                                  │
│       "playbook": "start_nodes.yml",                           │
│       "private_data_dir": "/home/localadmin/besu-ansible"      │
│     }                                                           │
│                           │                                     │
│                           ▼                                     │
│  4. Ansible Controller executes Besu playbook:                  │
│     - Configures Besu nodes                                     │
│     - Starts blockchain network                                 │
│     - Enables PQC cryptographic algorithms                      │
│                           │                                     │
│                           ▼                                     │
│  5. On success, CLI proceeds with slice creation                │
│     - Sends slice request to katana-nbi API                     │
│     - katana-mngr orchestrates the deployment                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Ansible Controller Requirements

The Ansible Controller must be running a Flask API that accepts playbook execution requests:

- **Endpoint**: `http://<ANSIBLE_IP>:5000/run_playbook`
- **Method**: POST
- **Payload**:
  ```json
  {
    "playbook": "start_nodes.yml",
    "private_data_dir": "/home/localadmin/besu-ansible"
  }
  ```

### Step 1: Ensure Ansible Controller is Running

The Ansible Controller server should have:
1. The `besu-ansible` playbooks at `/home/localadmin/besu-ansible`
2. A Flask API listening on port 5000
3. The `start_nodes.yml` playbook configured for your Besu nodes

### Step 2: Deploy with PQC Flag

```bash
# With PQC and slice file
katana slice add --pqc -f basicSlice.yaml

# The CLI will prompt:
# Enter the Ansible controller IP address [10.160.101.122]: 
# (Press Enter for default or type custom IP)
```

**What happens:**
1. CLI prompts for Ansible controller IP (default: 10.160.101.122)
2. CLI calls the Ansible API to execute `start_nodes.yml`
3. Besu blockchain nodes are started
4. If successful, slice creation proceeds
5. If Besu deployment fails, you can choose to continue or abort


### Besu Blockchain Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    BESU BLOCKCHAIN NETWORK                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│     ┌─────────┐      ┌─────────┐      ┌─────────┐              │
│     │ Besu    │◀────▶│ Besu    │◀────▶│ Besu    │              │
│     │ Node 1  │      │ Node 2  │      │ Node 3  │              │
│     │(Validator)     │(Validator)     │(Validator)              │
│     └─────────┘      └─────────┘      └─────────┘              │
│          │                │                │                    │
│          └────────────────┼────────────────┘                    │
│                           │                                     │
│                    ┌──────┴──────┐                              │
│                    │   Besu      │                              │
│                    │   Node 4    │                              │
│                    │ (Bootnode)  │                              │
│                    └─────────────┘                              │
│                                                                 │
│  Features:                                                      │
│  • IBFT 2.0 Consensus                                           │
│  • Post-Quantum Cryptographic Algorithms                        │
│  • Smart Contract Support                                       │
│  • Managed by Ansible Playbooks                                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Proxmox VM Deployment

The `--prox` flag creates VMs on a Proxmox cluster before slice creation.

### Step 1: Register Proxmox Cluster

```bash
katana proxmox add -f proxmox_cluster.yaml
```

Example `proxmox_cluster.yaml`:
```yaml
name: "Antares"
url: "https://10.160.100.11:8006"
username: "root@pam"
password: "your_password"
node: "cls01srv04"
```

### Step 2: Create VM Configuration

Example `proxmox_vms.yaml`:
```yaml
cluster_name: "Antares"

vms:
  - name: "katana-vm-1"
    template: "101"         # Template ID to clone
    cpu: 4
    ram: 4096               # MB
    storage_type: "fast:vm"
    disk_size: 20           # GB
    bridges:
      - name: "vmbr0"
        type: "management"
      - name: "vmbr1"
        type: "custom"
        ip: "192.168.10.10"
        netmask: "255.255.255.0"
        gateway: "192.168.10.1"

  - name: "katana-vm-2"
    template: "101"
    cpu: 2
    ram: 2048
    storage_type: "datastorage"
    disk_size: 30
    bridges:
      - name: "vmbr0"
        type: "management"
```

### Step 3: Deploy with Proxmox

```bash
# Just create VMs (no slice)
katana slice add --prox proxmox_vms.yaml

# Create VMs then slice
katana slice add --prox proxmox_vms.yaml -f basicSlice.yaml
```

### Proxmox CLI Commands

```bash
# List registered clusters
katana proxmox ls

# Add new cluster
katana proxmox add -f proxmox_cluster.yaml

# Remove cluster
katana proxmox rm <CLUSTER_ID>

# List VMs
katana proxmox vms

# Create VMs directly
katana proxmox vm-add -f proxmox_vms.yaml
```

---

## CLI Reference

### Slice Commands

| Command | Description |
|---------|-------------|
| `katana slice ls` | List all slices |
| `katana slice inspect <UUID>` | Show slice details |
| `katana slice add -f <FILE>` | Create slice from YAML |
| `katana slice add --pqc -f <FILE>` | Create slice with Besu blockchain |
| `katana slice add --prox <FILE>` | Create Proxmox VMs |
| `katana slice add --pqc --prox <VMS> -f <SLICE>` | Full deployment |
| `katana slice rm <UUID>` | Delete a slice |
| `katana slice modify -f <FILE> <UUID>` | Update a slice |
| `katana slice deployment-time <UUID>` | Show deployment time |
| `katana slice errors <UUID>` | Show slice errors |

### Infrastructure Commands

| Command | Description |
|---------|-------------|
| `katana nfvo ls` | List NFVOs |
| `katana nfvo add -f <FILE>` | Register NFVO |
| `katana vim ls` | List VIMs |
| `katana vim add -f <FILE>` | Register VIM |
| `katana location ls` | List locations |
| `katana location add -f <FILE>` | Add location |
| `katana function ls` | List functions |
| `katana function add -f <FILE>` | Add function |

### Proxmox Commands

| Command | Description |
|---------|-------------|
| `katana proxmox ls` | List Proxmox clusters |
| `katana proxmox add -f <FILE>` | Register cluster |
| `katana proxmox rm <ID>` | Remove cluster |
| `katana proxmox vms` | List all VMs |
| `katana proxmox vm-add -f <FILE>` | Create VMs |

### Kubernetes Commands

| Command | Description |
|---------|-------------|
| `katana k8s ls` | List K8s clusters |
| `katana k8s add -f <FILE>` | Add K8s cluster |
| `katana k8s rm <ID>` | Remove K8s cluster |
| `katana k8s migration` | Run migration |

---

## Configuration Files

### Directory Structure

```
katana-updated/
├── basicSlice.yaml          # Example slice configuration
├── proxmox_cluster.yaml     # Proxmox cluster registration
├── proxmox_vms.yaml         # Proxmox VM definitions
├── osm.json                 # OSM NFVO configuration
├── vimCore.json             # Core VIM configuration
├── vimEdge.json             # Edge VIM configuration
├── docker-compose.yaml      # Service definitions
├── bin/
│   ├── build.sh             # Build images
│   ├── deploy.sh            # Deploy services
│   └── stop.sh              # Stop services
└── templates/
    └── example_config_files/
        ├── Functions/       # Network function configs
        ├── location/        # Location configs
        └── nest/            # NEST templates
```

---

## Troubleshooting

### Common Issues

#### 1. Ansible Controller Connection Failed
```
Error triggering playbook: Connection refused
```
**Solution:**
- Verify the Ansible controller is running
- Check the IP address is correct
- Ensure port 5000 is open
- Test manually: `curl http://<IP>:5000/run_playbook`

#### 2. Proxmox Authentication Failed
```
Error: Failed to connect to Proxmox
```
**Solution:**
- Verify credentials in `proxmox_cluster.yaml`
- Check Proxmox API is accessible
- Ensure user has API permissions

#### 3. Slice Creation Timeout
```
Timeout Error
```
**Solution:**
- Check katana-mngr logs: `docker logs katana-mngr`
- Verify Kafka is running: `docker logs katana-kafka`
- Check MongoDB connection

### Useful Commands

```bash
# View logs
katana logs -l 100

# Check service status
docker-compose ps

# Restart services
docker-compose restart katana-nbi katana-mngr

# Full restart
bash bin/stop.sh && bash bin/deploy.sh
```

---

## Quick Reference

### Standard Slice Creation
```bash
katana slice add -f basicSlice.yaml
```

### PQC-Enabled Slice Creation (with Besu Blockchain)
```bash
katana slice add --pqc -f basicSlice.yaml
# Prompts for Ansible controller IP
# Deploys Besu blockchain first
# Then creates the slice
```


## Summary

| Deployment Type | Command | What It Does |
|-----------------|---------|--------------|
| **Standard** | `katana slice add -f slice.yaml` | Creates slice directly |
| **PQC** | `katana slice add --pqc -f slice.yaml` | Deploys Besu blockchain via Ansible, then creates slice |
| **Proxmox** | `katana slice add --prox vms.yaml` | Creates Proxmox VMs |


The `--pqc` flag is the key differentiator that enables post-quantum cryptographic security by deploying a Hyperledger Besu blockchain network before your slice, ensuring enhanced security for sensitive network slicing operations.
