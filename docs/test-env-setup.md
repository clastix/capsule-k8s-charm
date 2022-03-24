# Test Environment Setup

This guide will show you how to create a local installation of **Charmed Kubernetes**.

## Requirements

First of all, let's see what you need to setup the distribution:

* Ubuntu 20.04 OS image
* 32 GB RAM
* 150 GB additional HDD

## Setup

Once installed the OS with the given requirements, you have to partition the additional disk.

### HDD setup

This can be done with `parted`. Let's suppose the additional disk is named as `/dev/vdb`.

```bash
sudo parted /dev/vdb
> mklabel msdos
> mkpart primary ext4 0% 100%
> quit
```

This will create a primary partition with the whole disk size named `/dev/vdb1`.

Now it's time to create the file system. We can use an `ext4` one.

```bash
sudo mkfs.ext4 /dev/vdb1
```

Let's create the directory that will host the mount point and update the `/etc/fstab`:

```bash
sudo mkdir /opt/charmed
sudo echo "/dev/vdb1	/opt/charmed	ext4	defaults	0	1" >> /etc/fstab
sudo mount -a
```

### LXC setup

**Charmed Kubernetes** uses `lxc` as kubernetes nodes.

First of all, let's install `lxc` using `snap`:

```bash
sudo apt update
sudo apt install snapd
sudo snap install lxd
```

We need to assign a storage to them.

```bash
rm -rf /opt/charmed/lost+found/
# check if a "default" storage already exists and
# if so, delete it with:
# lxc storage delete default
lxc storage create default dir source=/opt/charmed
```

Run the `lxd` initialization script:

```bash
/snap/bin/lxd init
```

Answer the questions in this way:

* Would you like to use LXD clustering? (yes/no) [default=no]: `no`
* Do you want to configure a new storage pool? (yes/no) [default=yes]: `no`
* Would you like to connect to a MAAS server? (yes/no) [default=no]: `no`
* Would you like to create a new local network bridge? (yes/no) [default=yes]: `yes`
* What should the new bridge be called? [default=lxdbr0]: `lxdbr0`
* What IPv4 address should be used? (CIDR subnet notation, “auto” or “none”) [default=auto]: `auto`
* What IPv6 address should be used? (CIDR subnet notation, “auto” or “none”) [default=auto]: `none`
* Would you like the LXD server to be available over the network? (yes/no) [default=no]: `no`
* Would you like stale cached images to be updated automatically? (yes/no) [default=yes]: `yes`
* Would you like a YAML "lxd init" preseed to be printed? (yes/no) [default=no]: `yes`

### Juju setup

Juju should be installed from a snap:

```bash
sudo snap install juju --classic
```

Juju comes pre-configured to work with LXD.

A cloud created by using LXD containers on the local machine is known as `localhost` to Juju.

To begin, you need to create a Juju controller for this cloud:

```bash
juju bootstrap localhost
```

Juju creates a default model, but it is useful to create a new model for each project:

```bash
juju add-model k8s
```

### Charmed Kubernetes setup

All that remains is to deploy **Charmed Kubernetes**. A simple install can be achieved with one command:

```bash
juju deploy charmed-kubernetes
```

Check installation progress with:

```bash
watch -c juju status --color
```

## Troubleshooting

### Kubelet fail to start with errors related to inotify_add_watch

For example, `systemctl status snap.kubelet.daemon.service` may report the following error:

```
kubelet.go:1414] "Failed to start cAdvisor" err="inotify_add_watch /sys/fs/cgroup/cpu,cpuacct: no space left on device"
```

This problem usually is related to the kernel parameters, `fs.inotify.max_user_instances` and `fs.inotify.max_user_watches`.

At first, you should increase their values on the machine that is hosting the **Charmed Kubernetes** (`v1.23.4`) installation:

```bash
sysctl -w fs.inotify.max_user_instances=8192
sysctl -w fs.inotify.max_user_watches=1048576
```

Then, you can increase them also inside the worker containers:

```bash
juju config kubernetes-worker sysctl="{ fs.inotify.max_user_instances=8192 }"
juju config kubernetes-worker sysctl="{ fs.inotify.max_user_watches=1048576 }"
```

----

# Local Environment Setup

In case you don't need a production environment like the one described above, you can setup a minimal configuration locally using **kind**.

First, create your cluster with `kind`:

```bash
kind create cluster --name charmed-kubernetes
```

Then, deploy the **juju OLM** into your local cluster:

```bash
juju add-k8s --client mycluster --cluster-name=kind-charmed-kubernetes
```

Let's start the operator lifecycle manager on your cluster:

```bash
juju bootstrap mycluster
```

Now your cluster has the **juju OLM** controller installed.

From now, you can use `juju` to create **models** and **deploy** charms.

```bash
juju add-model hello-world
```

On Kubernetes, each model is put into a different namespace on the cluster. So you should see a `hello-world` namespace in your Kubernetes:

```bash
kubectl get namespaces
NAME                   STATUS   AGE
controller-mycluster   Active   160m
default                Active   162m
kube-node-lease        Active   162m
kube-public            Active   162m
kube-system            Active   162m
local-path-storage     Active   162m
hello-world            Active   79s
```

