# Charm Capsule Operator

## Description

This charm deploy and manage [Capsule](https://github.com/clastix/capsule) on Kubernetes.

The Capsule operator is a Python script that wrap the latest released version of Capsule, providing lifecycle management and handling events such as install, upgrade, integrate, and remove.

## Usage

To install the Capsule charm, run:

```bash
# Create dedicated namespace on k8s cluster
juju add-model capsule-system
# Deploy capsule along with the charm operator
juju deploy --trust ./charm-k8s-capsule.charm --resource capsule-image=clastix/capsule:v0.1.1
```
