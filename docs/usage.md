## Usage

### Install

To install the charm, run:

```bash
# Create dedicated namespace on k8s cluster
juju add-model capsule-system
# Deploy capsule along with the charm operator
juju deploy charm-k8s-capsule
```

### Configure

To configure the charm, run:

```bash
# Example: juju config charm-k8s-capsule key=value
juju config charm-k8s-capsule force-tenant-prefix=true
juju config charm-k8s-capsule user-groups=capsule.clastix.io,gas.clastix.io,oil.clastix.io
```

In case you have multiple `CapsuleConfiguration` instances, you can modify a specific one by using the `capsule-configuration-name` parameter with the name of the resource you want to modify:

```bash
juju config charm-k8s-capsule capsule-configuration-name=capsule-configuration-2 force-tenant-prefix=true
```

The configurable parameters are:

| **name**                    | **description**                                              | type    | **default**          | references                                                   |
| --------------------------- | ------------------------------------------------------------ | ------- | -------------------- | ------------------------------------------------------------ |
| `user-groups`               | Comma-separated list of user groups (example: `oil.capsule.io,gas.capsule.io`). | string  | `capsule.clastix.io` | [userGroups](https://capsule.clastix.io/docs/general/references/#capsule-configuration) |
| `force-tenant-prefix`       | Force to have a tenant prefix.                               | boolean | `false`              | [forceTenantPrefix](https://capsule.clastix.io/docs/general/references/#capsule-configuration) |
| `protected-namespace-regex` | Disallows creation of namespaces matching the passed regexp. | string  | `""`                 | [protectedNamespaceRegex](https://capsule.clastix.io/docs/general/references/#capsule-configuration) |

