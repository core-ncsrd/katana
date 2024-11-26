# Changelog

All notable changes to this project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.3.6] - 06/12/2022

### 2.3.6 Added

- NEAT - APEX policy engines Integration

### 2.3.6 Changed

- Bug Fixes

## [2.3.5] - 16/12/2021

### 2.3.5 Added

- APEX policy engine integration

## [2.3.4] - 06/12/2021

### 2.3.4 Added

- Slice D2 Operations
  - Stop Network Service
  - Add Network Service
  - Restart Network Service with specific constraints

## [2.3.3] - 22/11/2021

### 2.3.3 Added

- Prometheus Alertmanager
- Prometheus alerts for NFV
- API for receiving external alerts

### 2.3.3 Changed

- Fixed Monitoring - Shared Functions Bug
- Check for running slices before stopping SM

## [2.3.2] - 04/11/2021

### 2.3.2 Added

- Location Registry
- Jenkinsfile.kill for destroy pipeline

### 2.3.2 Changed

- Version and Server URL on swagger

## [2.3.1] - 29/10/2021

### 2.3.1 Changed

- Updated binaries for building, deplpoying, stopping, and uninstalling Katana
- Updated CI/CD pipelines
- Removed deprecated UI container

## [2.3.0] - 12/11/2020

### 2.3.0 Added

- CI/CD pipeline:
  - Multibranch Pipeline Job
  - Releases Pipeline Job

### 2.3.0 Changed

- Scripts for building, starting, testing and packaging Katana
- Minor errors on Monitoring module
- New containers based on public one:
  - katana-grafana
  - katana-prometheus
  - katana-swagger

## [2.2.8] - 15/10/2020

### 2.2.8 Added

- Support for multiple shared NSSIs among slices

## [2.2.7] - 04/09/2020

### 2.2.7 Added

- Support for OpenStack Stein release
- Support for Open Source MANO release 8
- Bootstrap API (/api/bootstrap) which allows Katana configuration with a single config file

### 2.2.7 Changed

- Handle failed to start Network Services from Open Source MANO

## [2.2.6] - 30/07/2020

### 2.2.6 Added

- Monitoring module: Prometheus and Grafana containers
- Integrate ODL prometheus exporter to collect traffic metrics per flow
- Per slice Network Service Status monitoring
- Per slice VM monitoring
- Katana Home Dashboard on Grafana
- Create a Grafana Dashboard for every new slice

### 2.2.6 Changed

- base_slice_des bug fixed

## [2.2.5] - 02/06/2020

### 2.2.5 Changed

Integration with ELCM:

- Added `?nsd-id={id}&nfvo-id={id}` query parameters in `/api/nslist` endpoint
- Removed `nfvo-id` from NEST
- Explicitily define a string location in NS placement in service_descriptor part of the NEST

## [2.2.4] - 20/05/2020

### 2.2.4 Added

- katana CLI: Delete multiple slices with a single command
- katana CLI: --force option for Errored slices
- Expose Kafka and swagger to external components

### 2.2.4 Changed

- Improved Slice Termination process
- Improved Binary files for start, stop
- Katana CLI: More accurate error messages
- Bug fixed on Slice Termination process
- ODL-WIM Plugin: Send messages using Kafka

## [2.2.3] - 04/05/2020

### 2.2.3 Added

- Support for OSM Release 7
- katana logs --limit feature

### 2.2.3 Changed

- Minor bug fixes

## [2.2.2] - 08/04/2020

### 2.2.2 Added

- Set the Tenant Quotas based on the slice requirements for OpenStack VIMs

### 2.2.2 Changed

- Minor bug fixes in katana-cli

## [2.2.1] - 11/03/2020

### 2.2.1 Added

- API for retrieving OpenStack max and available resources

## [2.2.0] - 20/02/2020

### 2.2.0 Added

- Support for NEAT UE Policy System

### 2.2.0 Changed

- Network Functions DB instead of SST
- Slice Mapping chooses the most suitable Functions from the database
- Removed PDU db
- Improved Slice Deletion process

## [2.1.1] - 03/02/2020

### 2.1.1 Added

- Support (API and DB) for external Policy System Engine

### 2.1.1 Changed

- Required fields on json schema
- Readmec file
- GST Terminology
- Wiki

## [2.1.0] - 16/01/2020

### 2.1.0 Added

- Kafka and Zookeeper Containers | Split katana-mngr to 2 processes-containers: katana-nbi and katana-mngr | Created Kafka producers & consumer to exchange messages between containers
- Required field for VIM, NFVO, WIM, EMS, PDU components
- Check for that the required fields stay the same when update one of these components
- Index in mongo to ID field for these components to avoid duplicate IDs
- Support for "test" types of EMS and WIM
- This changelog

### 2.1.0 Changed

- Appearance of "katana sst ls" command
- Customized katana-cli to print http body on httperror case
- Fixed bugs on slice deletion process

## [2.0.0] - 08/01/2020

### 2.0.0 Added

- New Information model for slice creation (GST)
- Slice mapping process | Create NEST based on GST and supported SST
- Added Supported SST instead of Registered Services
- Hunab-readable Unique ID for each component
- New Resource API per location

### 2.0.0 Changed

- Upgrade swagger to Open APIs 3.0.1
- New example config files
- Redesigned the slice deletion process
- VIM admin account bug fixed
- Katana CLI ls output appearance
