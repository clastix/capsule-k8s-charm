# Charm Capsule Operator

## Description

This charm deploy and manage [Capsule](https://github.com/clastix/capsule) on Kubernetes.

The Capsule operator is a Python script that wrap the latest released version of Capsule, providing life-cycle management and handling events such as install, upgrade, integrate, and remove.

## Usage

### Install

To install the charm, run:

```bash
# Create dedicated namespace on k8s cluster
juju add-model capsule-system
# Deploy capsule along with the charm operator
juju deploy --trust ./charm-k8s-capsule.charm --resource capsule-image=clastix/capsule:v0.1.1
```

### Configure

To configure the charm, run:

```bash
juju config charm-k8s-capsule key=value
# Example: juju config charm-k8s-capsule force-tenant-prefix=true
```

In case you have multiple `CapsuleConfiguration` instances, you can modify a specific one by using the `capsule-configuration-name` parameter with the name of the resource you want to modify:

```bash
juju config charm-k8s-capsule capsule-configuration-name=capsule-configuration-2 force-tenant-prefix=true
```

For available parameters, take a look at `config.yaml` file in this repository.

