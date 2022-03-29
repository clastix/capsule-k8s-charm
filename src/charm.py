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
import lightkube
import yaml
from http import HTTPStatus

from os import path
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from lightkube import Client, codecs
from lightkube.core.exceptions import ApiError

logger = logging.getLogger(__name__)
TEMPLATE_DIR = "src/templates/"

_capsule_configuration_crd = None
def get_capsule_configuration():
    """Function to retrieve CapsuleConfiguration class."""
    global _capsule_configuration_crd
    if _capsule_configuration_crd == None:
        _capsule_configuration_crd = create_capsule_configuration()
    return _capsule_configuration_crd

def create_capsule_configuration():
    with open(TEMPLATE_DIR + "install.yaml.j2") as f:
        logger.info("collecting manifests.")
        for resource in codecs.load_all_yaml(f):
            
            if resource.kind != "CustomResourceDefinition":
                continue
            # List of custom resource definition to be created.
            if resource.spec.names.kind == "CapsuleConfiguration":
                return lightkube.generic_resource.create_global_resource(
                    group=resource.spec.group, 
                    version=resource.spec.versions[0].name, 
                    kind=resource.spec.names.kind, 
                    plural=resource.spec.names.plural,
                    verbs=None
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
        """Retrieve capsule contianer image internally from charm."""
        container_info_path = self.model.resources.fetch(image_name)
        with open(container_info_path) as cip:
            return yaml.safe_load(cip)["registrypath"]

    def _on_install(self, _) -> None:
        """Handle the install event, create Kubernetes resources."""
        self.unit.status = MaintenanceStatus("creating kubernetes resources.")
        try:
            logger.info("create kubernetes resources.")
            if self._create_kubernetes_resources():
                self.unit.status = ActiveStatus("succesfully installed {} charm.".format(self.meta.name))
            else:
                self.unit.status = BlockedStatus("{} creation failed.".format(self.meta.name))
        except ApiError:
            logger.error(traceback.format_exc())
            self.unit.status = BlockedStatus("{} creation failed.".format(self.meta.name))

        return

    def _on_capsule_configuration_changed(self, event) -> None:
        """Handle the config_changed event for CapsuleConfiguration resource."""
        self.unit.status = MaintenanceStatus("changing CapsuleConfiguration resource.")
        capsule_configuration_crd = get_capsule_configuration()

        # In config changed event the resource should already be created, so we can retrieve this.
        capsule_configuration_res = self.client.get(
            capsule_configuration_crd,
            self.model.config["capsule-configuration-name"]
        )

        # Update resource attributes.
        capsule_configuration_res.spec["userGroups"] = self.model.config["user-groups"].split(",")
        capsule_configuration_res.spec["forceTenantPrefix"] = self.model.config["force-tenant-prefix"]
        capsule_configuration_res.spec["protectedNamespaceRegex"] = self.model.config["protected-namespace-regex"]

        try:
            logger.info("changing configuration for %s resource.", capsule_configuration_res.kind)
            self.client.replace(capsule_configuration_res)
            self.unit.status = ActiveStatus("%s succesfully changed.".format(capsule_configuration_res.kind))
        except ApiError:
            logger.debug("failed to update resource %s.", capsule_configuration_res.kind)
            self.unit.status = BlockedStatus("{} creation failed.".format(capsule_configuration_res.kind))
            raise

        return
        
    def _create_kubernetes_resources(self) -> bool:
        """Iterates over manifests in the templates directory and applies them to the cluster."""
        with open(TEMPLATE_DIR + "install.yaml.j2") as f:
            logger.info("collecting manifests.")
            for resource in codecs.load_all_yaml(f, context=self._context):
                logger.info("creating resource %s from manifest.", resource.kind)
                try:
                    self.client.create(resource)
                    logger.info("resources %s created.", resource.kind)
                except ApiError as e:
                    if e.status.code == HTTPStatus.CONFLICT:
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

    def _create_custom_resource(self, crd, resource) -> None:
        """Create a custom resource from a CRD."""
        if not path.exists(TEMPLATE_DIR + "install-{}.yaml.j2".format(resource.spec.names.kind)):
            logger.error("no manifest file for resource %s has been found.", resource.spec.names.kind)
            raise

        with open(TEMPLATE_DIR + "install-{}.yaml.j2".format(resource.spec.names.kind)) as f_crd:

            # Create resource with updated values (stored in _context)
            for resource_crd in codecs.load_all_yaml(f_crd, self._context):
                cr = crd(
                    kind=resource_crd.kind,
                    apiVersion=resource.spec.group + "/" + resource.spec.versions[0].name,
                    spec=resource_crd.spec, 
                    metadata=resource_crd.metadata
                )
                logger.info("creating %s resource.", resource_crd.kind)
                try:
                    self.client.create(cr)
                except ApiError as e:
                    if e.status.code == HTTPStatus.CONFLICT:
                        logger.info("replacing resource: %s.", str(resource.to_dict()))
                        self.client.replace(resource)
                    else:
                        logger.debug("failed to create resource: %s.", str(resource.to_dict()))
                        raise

        return


if __name__ == "__main__":
    main(CharmK8SCapsuleCharm)
