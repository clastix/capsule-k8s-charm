#!/usr/bin/env python3
# Copyright 2022 Clastix
# See LICENSE file for licensing details.


import logging
from pathlib import Path

import lightkube
import pytest
import yaml
from lightkube import Client, codecs
from lightkube.resources.admissionregistration_v1 import (
    MutatingWebhookConfiguration,
    ValidatingWebhookConfiguration,
)
from lightkube.resources.apiextensions_v1 import CustomResourceDefinition
from lightkube.resources.core_v1 import Secret, Service
from lightkube.resources.rbac_authorization_v1 import ClusterRoleBinding
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Build the charm-under-test and deploy it together with related charms."""
    charm = await ops_test.build_charm(".")
    resources = {"capsule-image": METADATA["resources"]["capsule-image"]["upstream-source"]}
    await ops_test.model.deploy(charm, resources=resources, application_name=APP_NAME, trust=True)

    # issuing dummy update_status just to trigger an event
    await ops_test.model.set_config({"update-status-hook-interval": "10s"})

    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)
    assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"

    # effectively disable the update status from firing
    await ops_test.model.set_config({"update-status-hook-interval": "60m"})


@pytest.mark.abort_on_fail
async def test_kubernetes_resources_created(ops_test: OpsTest):
    """Test if kubernetes resources have been created properly."""
    client = Client()

    # If any of these fail, an exception is raised and the test will fail
    client.get(CustomResourceDefinition, name="tenants.capsule.clastix.io")
    client.get(CustomResourceDefinition, name="capsuleconfigurations.capsule.clastix.io")
    client.get(ClusterRoleBinding, name="capsule-manager-rolebinding")
    client.get(Secret, name="capsule-ca", namespace=ops_test.model_name)
    client.get(Secret, name="capsule-tls", namespace=ops_test.model_name)
    client.get(Service, name="capsule-webhook-service", namespace=ops_test.model_name)
    client.get(
        Service, name="capsule-controller-manager-metrics-service", namespace=ops_test.model_name
    )
    client.get(
        MutatingWebhookConfiguration,
        name="capsule-mutating-webhook-configuration",
        namespace=ops_test.model_name,
    )
    client.get(
        ValidatingWebhookConfiguration,
        name="capsule-validating-webhook-configuration",
        namespace=ops_test.model_name,
    )


@pytest.mark.abort_on_fail
async def test_tenant_creation(ops_test: OpsTest):
    """Test if tenant could be created properly."""
    client = Client()

    tenant = lightkube.generic_resource.create_global_resource(
        group="capsule.clastix.io",
        version="v1beta1",
        kind="Tenant",
        plural="tenants",
        verbs=None,
    )
    with open("./tests/integration/tenant.yaml", encoding="utf-8") as tenant_manifest:
        tenant_crd = codecs.load_all_yaml(tenant_manifest)
        _tenant = tenant(
            kind=tenant_crd[0].kind,
            apiVersion="capsule.clastix.io/v1beta1",
            spec=tenant_crd[0].spec,
            metadata=tenant_crd[0].metadata,
        )

        # wait for capsule ready
        await ops_test.model.wait_for_idle(wait_for_active=True, idle_period=60, status="active")
        client.create(_tenant)
