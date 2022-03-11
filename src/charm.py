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

from importlib.abc import ResourceReader
from glob import glob
from os import path
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from lightkube import Client, codecs
from lightkube.generic_resource import create_namespaced_resource
from lightkube.core.exceptions import ApiError

logger = logging.getLogger(__name__)


class CharmK8SCapsuleCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()

    def __init__(self, *args) -> None:
        super().__init__(*args)
        self._context = {
            "namespace": self.model.config["namespace"], 
            "app_name": self.model.config["name"]
        }
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self._stored.set_default(things=[])

    def _on_install(self, _) -> None:
        """Handle the install event, create Kubernetes resources."""
        self.unit.status = MaintenanceStatus("creating kubernetes resources")
        try:
            logger.info("create kubernetes resources.")
            self._create_kubernetes_resources()
        except ApiError:
            logger.error(traceback.format_exc())
            self.unit.status = BlockedStatus("kubernetes resource creation failed")

    def _create_kubernetes_resources(self) -> bool:
        """Iterates over manifests in the templates directory and applies them to the cluster."""
        client = Client()
        with open("src/templates/install.yaml.j2") as f:
            logger.info("collecting manifests.")
            for resource in codecs.load_all_yaml(f, context=self._context):
                try:
                    logger.info("creating resource %s from manifest.", resource.kind)
                    client.create(resource)
                    logger.info("resources %s created.", resource.kind)
                except ApiError as e:
                    if e.status.code == 409:
                        logger.info("replacing resource: %s.", str(resource.to_dict()))
                        client.replace(resource)
                    else:
                        logger.debug("failed to create resource: %s.", str(resource.to_dict()))
                        raise
                
                try:
                    if resource.kind == "CustomResourceDefinition" and path.exists("src/templates/install-{}.yaml.j2".format(resource.spec.names.kind)):
                        with open("src/templates/install-{}.yaml.j2".format(resource.spec.names.kind)) as f_crd:
                            logger.info("creating CRD %s for %s.", resource.kind, resource.spec.names.kind)
                            CRD = lightkube.generic_resource.create_global_resource(
                                group=resource.spec.group, 
                                version=resource.spec.versions[0].name, 
                                kind=resource.spec.names.kind, 
                                plural=resource.spec.names.plural,
                                verbs=None
                            )
                            for resource_crd in codecs.load_all_yaml(f_crd):
                                crd = CRD(
                                    kind=resource_crd.kind,
                                    apiVersion=resource.spec.group + "/" + resource.spec.versions[0].name,
                                    spec=resource_crd.spec, 
                                    metadata=resource_crd.metadata
                                )
                                logger.info("creating %s resource.", resource_crd.kind)
                                client.wait(resource.__class__, name=resource.metadata.name, for_conditions=['Established'])
                                client.create(crd)
                except ApiError as e:
                    if e.status.code == 409:
                        logger.info("replacing resource: %s.", str(resource.to_dict()))
                        client.replace(resource)
                    else:
                        logger.debug("failed to create resource: %s.", str(resource.to_dict()))
                        raise

        return True

    def _on_config_changed(self, _) -> None:
        """Just an example to show how to deal with changed configuration.

        TEMPLATE-TODO: change this example to suit your needs.
        If you don't need to handle config, you can remove this method,
        the hook created in __init__.py for it, the corresponding test,
        and the config.py file.

        Learn more about config at https://juju.is/docs/sdk/config
        """
        return


if __name__ == "__main__":
    main(CharmK8SCapsuleCharm)
