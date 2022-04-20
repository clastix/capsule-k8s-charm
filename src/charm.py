#!/usr/bin/env python3
# Copyright 2022 Clastix
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm the service.

Refer to the following post for a quick-start guide that will help you
develop a new k8s charm using the Operator Framework:

    https://discourse.charmhub.io/t/4208
"""

import logging
import traceback
from http import HTTPStatus
from os import path
from typing import List

import lightkube
from lightkube import Client, codecs
from lightkube.core.exceptions import ApiError
from lightkube.models.core_v1 import SecretVolumeSource, Volume, VolumeMount
from lightkube.resources.apps_v1 import StatefulSet
from lightkube.resources.core_v1 import Service
from ops.charm import CharmBase, WorkloadEvent
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus

logger = logging.getLogger(__name__)
TEMPLATE_DIR = "src/templates/"
VOLUME_MOUNT = "/tmp/k8s-webhook-server/serving-certs"
VOLUME_CERT = "cert"
CAPSULE_CONFIGURATION_CRD = None


def get_capsule_configuration():
    """Function to retrieve CapsuleConfiguration class."""
    # pylint: disable=w0603
    global CAPSULE_CONFIGURATION_CRD
    if CAPSULE_CONFIGURATION_CRD is None:
        CAPSULE_CONFIGURATION_CRD = create_capsule_configuration()
    return CAPSULE_CONFIGURATION_CRD


# pylint: disable=R1710
def create_capsule_configuration():
    """Create CapsuleConfiguration class."""
    with open(TEMPLATE_DIR + "install.yaml.j2", encoding="utf-8") as cc_file:
        logger.info("collecting manifests.")
        for resource in codecs.load_all_yaml(cc_file):
            if resource.kind != "CustomResourceDefinition":
                continue
            # List of custom resource definition to be created.
            if resource.spec.names.kind == "CapsuleConfiguration":
                return lightkube.generic_resource.create_global_resource(
                    group=resource.spec.group,
                    version=resource.spec.versions[0].name,
                    kind=resource.spec.names.kind,
                    plural=resource.spec.names.plural,
                    verbs=None,
                )


class CapsuleOperatorK8sCharm(CharmBase):
    """Charm the service."""

    client = Client()

    def __init__(self, *args) -> None:
        super().__init__(*args)

        # We have to collect all the available configurations
        # in order to fill the Jinja2 manifest templates.
        self._context = {
            "namespace": self.model.config["namespace"],
            "app_name": self.model.config["name"],
            "user_groups": self.model.config["user-groups"],
            "force_tenant_prefix": self.model.config["force-tenant-prefix"],
            "protected_namespace_regex": self.model.config["protected-namespace-regex"],
        }

        # Assign hook functions to events.
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.capsule_pebble_ready, self._on_capsule_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_capsule_configuration_changed)

        self._patch_capsule_services()

    def _statefulset_patched(self) -> bool:
        """Slightly naive check to see if the StatefulSet has already been patched."""
        ss: StatefulSet = self.client.get(
            StatefulSet, name=self.app.name, namespace=self.model.config["namespace"]
        )
        expected = VolumeMount(mountPath=VOLUME_MOUNT, name=VOLUME_CERT)
        return expected in ss.spec.template.spec.containers[1].volumeMounts

    def _patch_statefulset(self) -> None:
        """Patch Capsule StatefulSet to add Volumes."""
        ss: StatefulSet = self.client.get(
            StatefulSet, name=self.app.name, namespace=self.model.config["namespace"]
        )
        ss.spec.template.spec.volumes.extend(self._capsule_volumes)
        ss.spec.template.spec.containers[1].volumeMounts.extend(self._capsule_volume_mounts)

        self.client.patch(
            StatefulSet, name=self.app.name, obj=ss, namespace=self.model.config["namespace"]
        )

    def _patch_capsule_services(self) -> None:
        """Add node selector to Capsule services."""

        # retrieve capsule services
        service_webhook: Service = self.client.get(
            Service, name="capsule-webhook-service", namespace=self.model.config["namespace"]
        )
        service_metrics: Service = self.client.get(
            Service,
            name="capsule-controller-manager-metrics-service",
            namespace=self.model.config["namespace"],
        )
        capsule_services = [service_webhook, service_metrics]

        for service in capsule_services:
            service_changed = False
            # remove default selector
            if service.spec.selector.get("control-plane"):
                service.spec.selector.pop("control-plane")
                service_changed = True
            # add charm custom selector
            if service.spec.selector.get("app.kubernetes.io/name") is None:
                service.spec.selector.update({"app.kubernetes.io/name": "charm-k8s-capsule"})
                service_changed = True
            # apply changes replacing service
            if service_changed:
                self.client.replace(
                    name=service.metadata.name,
                    obj=service,
                    namespace=self.model.config["namespace"],
                )

    @property
    def _capsule_volumes(self) -> List[Volume]:
        """Returns the additional volumes required by Capsule."""
        # Get the service account details so we can reference it's token
        return [
            Volume(
                name=VOLUME_CERT,
                secret=SecretVolumeSource(
                    secretName="capsule-tls",
                    defaultMode=420,
                ),
            )
        ]

    @property
    def _capsule_volume_mounts(self) -> List[VolumeMount]:
        """Returns the additional volume mounts for the capsule containers."""
        return [
            VolumeMount(
                mountPath=VOLUME_MOUNT,
                name=VOLUME_CERT,
            ),
        ]

    def _on_install(self, _) -> None:
        """Handle the install event, create Kubernetes resources."""
        self.unit.status = MaintenanceStatus("creating kubernetes resources.")
        try:
            logger.info("create kubernetes resources.")
            if self._create_kubernetes_resources():
                self.unit.status = ActiveStatus()
            else:
                self.unit.status = BlockedStatus("creation failed.")
        except ApiError:
            logger.error(traceback.format_exc())
            self.unit.status = BlockedStatus("creation failed.")

    def _cli_flags(self) -> str:
        """Return the cli arguments to pass to agent."""
        # pylint: disable=line-too-long
        return " --enable-leader-election --zap-encoder=console --zap-log-level=debug --configuration-name=capsule-default"

    def _on_capsule_pebble_ready(self, event: WorkloadEvent) -> None:
        """Define and start a workload using the Pebble API."""
        # Get a reference the container attribute on the PebbleReadyEvent
        container = event.workload
        # Define an initial Pebble layer configuration
        pebble_layer = {
            "summary": "capsule layer",
            "description": "pebble config layer for capsule",
            "services": {
                "capsule": {
                    "override": "replace",
                    "summary": "capsule",
                    "command": f"/manager {self._cli_flags()}",
                    "startup": "enabled",
                    "environment": {"NAMESPACE": self.model.config["namespace"]},
                    "on-failure": "ignore",
                }
            },
        }
        # Add initial Pebble config layer using the Pebble API
        container.add_layer("capsule", pebble_layer, combine=True)
        # Autostart any services that were defined with startup: enabled
        container.autostart()

        # Setup volume mounts for capsule
        logger.info(self._statefulset_patched())
        if not self._statefulset_patched():
            logger.info(f"patching {self.app.name} StatefulSet")
            self._patch_statefulset()
            self.unit.status = MaintenanceStatus("waiting for changes to apply")

        self.unit.status = ActiveStatus()

    # pylint: disable=W0613
    def _on_capsule_configuration_changed(self, event) -> None:
        """Handle the config_changed event for CapsuleConfiguration resource."""
        self.unit.status = MaintenanceStatus("changing CapsuleConfiguration resource.")
        capsule_configuration_crd = get_capsule_configuration()

        # In config changed event the resource should already be created, so we can retrieve this.
        capsule_configuration_res = self.client.get(
            capsule_configuration_crd, self.model.config["capsule-configuration-name"]
        )

        # Update resource attributes.
        # pylint: disable=line-too-long
        capsule_configuration_res.spec["userGroups"] = self.model.config["user-groups"].split(",")
        # pylint: disable=line-too-long
        capsule_configuration_res.spec["forceTenantPrefix"] = self.model.config[
            "force-tenant-prefix"
        ]
        # pylint: disable=line-too-long
        capsule_configuration_res.spec["protectedNamespaceRegex"] = self.model.config[
            "protected-namespace-regex"
        ]

        try:
            logger.info("changing configuration for %s resource.", capsule_configuration_res.kind)
            self.client.replace(capsule_configuration_res)
            self.unit.status = ActiveStatus()
        except ApiError:
            logger.debug("failed to update resource %s", capsule_configuration_res.kind)
            self.unit.status = BlockedStatus(f"{capsule_configuration_res.kind} creation failed.")
            raise

    def _create_kubernetes_resources(self) -> bool:
        """Iterates over manifests in the templates directory and applies them to the cluster."""
        with open(TEMPLATE_DIR + "install.yaml.j2", encoding="utf-8") as kube_manifests:
            logger.info("collecting manifests.")
            for resource in codecs.load_all_yaml(kube_manifests, context=self._context):
                logger.info("creating resource %s from manifest.", resource.kind)
                try:
                    self.client.create(resource)
                    logger.info("resources %s created.", resource.kind)
                except ApiError as err:
                    if err.status.code == HTTPStatus.CONFLICT:
                        logger.info("replacing resource: %s.", str(resource.to_dict()))
                        self.client.replace(resource)
                    else:
                        logger.debug("failed to create resource: %s.", str(resource.to_dict()))
                        raise

                # List of Capsule CRDs to create.
                if resource.kind == "CustomResourceDefinition":
                    if resource.spec.names.kind == "CapsuleConfiguration":
                        capsule_configuration_crd = get_capsule_configuration()
                        self._create_custom_resource(capsule_configuration_crd, resource)

        return True

    def _create_custom_resource(self, crd, resource) -> bool:
        """Create a custom resource from a CRD."""
        if not path.exists(TEMPLATE_DIR + f"install-{resource.spec.names.kind}.yaml.j2"):
            logger.error(
                "no manifest file for resource %s has been found.", resource.spec.names.kind
            )
            return False

        # pylint: disable=line-too-long
        with open(
            TEMPLATE_DIR + f"install-{resource.spec.names.kind}.yaml.j2", encoding="utf-8"
        ) as f_crd:

            # Create resource with updated values (stored in _context)
            for resource_crd in codecs.load_all_yaml(f_crd, self._context):
                custom_res = crd(
                    kind=resource_crd.kind,
                    apiVersion=resource.spec.group + "/" + resource.spec.versions[0].name,
                    spec=resource_crd.spec,
                    metadata=resource_crd.metadata,
                )
                logger.info("creating %s resource.", resource_crd.kind)
                try:
                    self.client.create(custom_res)
                except ApiError as err:
                    if err.status.code == HTTPStatus.CONFLICT:
                        logger.info("replacing resource: %s.", str(resource.to_dict()))
                        self.client.replace(resource)
                    else:
                        logger.debug("failed to create resource: %s.", str(resource.to_dict()))
                        raise

        return True


if __name__ == "__main__":
    main(CapsuleOperatorK8sCharm)
