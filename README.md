# Charm Capsule Operator

## Description

**Capsule** implements a multi-tenant and policy-based  environment in your Kubernetes cluster. It is designed as a  micro-services-based ecosystem with the minimalist approach, leveraging  only on upstream Kubernetes.

This repository contains a Charm Operator for deploying **Capsule** in a Charmed Kubernetes cluster.

## Usage

### Install

To install the charm, run:

```bash
# Create dedicated namespace on k8s cluster
juju add-model capsule-system
# Deploy capsule along with the charm operator
juju deploy --trust capsule-k8s
```

## References

* [Capsule](https://github.com/clastix/capsule)
* [OCI Image](https://quay.io/repository/clastix/capsule?tab=tags&tag=latest)

## Documentation

Read the official documentation here: [capsule.clastix.io](https://capsule.clastix.io/)

