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

import lightkube
import yaml
from lightkube import Client, codecs
from lightkube.core.exceptions import ApiError
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus

logger = logging.getLogger(__name__)
TEMPLATE_DIR = "src/templates/"

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


class CharmK8SCapsuleCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()
    client = Client()

    def __init__(self, *args) -> None:
        super().__init__(*args)

        # Retrieve capsule container image from charm
        capsule_image = self.get_container_image(image_name="capsule-image")
        if capsule_image == "" or capsule_image is None:
            raise Exception("No container image found.")

        # We have to collect all the available configurations
        # in order to fill the Jinja2 manifest templates.
        self._context = {
            "namespace": self.model.config["namespace"],
            "app_name": self.model.config["name"],
            "capsule_image": capsule_image,
            "user_groups": self.model.config["user-groups"],
            "force_tenant_prefix": self.model.config["force-tenant-prefix"],
            "protected_namespace_regex": self.model.config["protected-namespace-regex"],
        }

        # Assign hook functions to events.
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_capsule_configuration_changed)
        self._stored.set_default(things=[])

    def get_container_image(self, image_name: str) -> str:
        """Retrieve capsule container image internally from charm."""
        container_info_path = self.model.resources.fetch(image_name)
        with open(container_info_path, encoding="utf-8") as cip:
            return yaml.safe_load(cip)["registrypath"]

    def _on_install(self, _) -> None:
        """Handle the install event, create Kubernetes resources."""
        self.unit.status = MaintenanceStatus("creating kubernetes resources.")
        try:
            logger.info("create kubernetes resources.")
            if self._create_kubernetes_resources():
                self.unit.status = ActiveStatus(f"successfully installed {self.meta.name} charm.")
            else:
                self.unit.status = BlockedStatus(f"{self.meta.name} creation failed.")
        except ApiError:
            logger.error(traceback.format_exc())
            self.unit.status = BlockedStatus(f"{self.meta.name} creation failed.")

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
            self.unit.status = ActiveStatus(
                f"{capsule_configuration_res.kind} successfully changed."
            )
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
    main(CharmK8SCapsuleCharm)
