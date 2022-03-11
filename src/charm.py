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
from glob import glob

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from lightkube import Client, codecs
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
        self.framework.observe(self.on.capsule_pebble_ready, self._on_capsule_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.fortune_action, self._on_fortune_action)
        self._stored.set_default(things=[])

    def _on_install(self, _) -> None:
        """Handle the install event, create Kubernetes resources."""
        self.unit.status = MaintenanceStatus("creating kubernetes resources")
        try:
            self._create_kubernetes_resources()
        except ApiError:
            logger.error(traceback.format_exc())
            self.unit.status = BlockedStatus("kubernetes resource creation failed")

    def _on_capsule_pebble_ready(self, event) -> None:
        """Define and start a workload using the Pebble API.

        TEMPLATE-TODO: change this example to suit your needs.
        You'll need to specify the right entrypoint and environment
        configuration for your specific workload. Tip: you can see the
        standard entrypoint of an existing container using docker inspect

        Learn more about Pebble layers at https://github.com/canonical/pebble
        """
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
                    "command": "/manager",
                    "startup": "enabled",
                    "environment": {
                        "NAMESPACE": self.model.config["namespace"]
                    },
                }
            },
        }
        # Add initial Pebble config layer using the Pebble API
        container.add_layer("capsule", pebble_layer, combine=True)
        # Autostart any services that were defined with startup: enabled
        container.autostart()
        # Learn more about statuses in the SDK docs:
        # https://juju.is/docs/sdk/constructs#heading--statuses
        self.unit.status = ActiveStatus()

    def _create_kubernetes_resources(self) -> bool:
        """Iterates over manifests in the templates directory and applies them to the cluster."""
        client = Client()
        # create_resources = ["cluster_roles", "config_maps", "secrets", "services"]
        # for manifest in create_resources:
        for manifest in glob("src/templates/*.yaml.j2"):
            # with open(f"src/templates/{manifest}.yaml.j2") as f:
            with open(manifest) as f:
                for resource in codecs.load_all_yaml(f, context=self._context):
                    try:
                        client.create(resource)
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
#        current = self.config["thing"]
#        if current not in self._stored.things:
#            logger.debug("found a new thing: %r", current)
#            self._stored.things.append(current)
        return

    def _on_fortune_action(self, event) -> None:
        """Just an example to show how to receive actions.

        TEMPLATE-TODO: change this example to suit your needs.
        If you don't need to handle actions, you can remove this method,
        the hook created in __init__.py for it, the corresponding test,
        and the actions.py file.

        Learn more about actions at https://juju.is/docs/sdk/actions
        """
        fail = event.params["fail"]
        if fail:
            event.fail(fail)
        else:
            event.set_results({"fortune": "A bug in the code is worth two in the documentation."})


if __name__ == "__main__":
    main(CharmK8SCapsuleCharm)
