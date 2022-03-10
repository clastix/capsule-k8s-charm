# Copyright 2022 Clastix
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest
from unittest.mock import Mock

from charm import CharmK8SCapsuleCharm
from ops.model import ActiveStatus
from ops.testing import Harness


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(CharmK8SCapsuleCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_config_changed(self):
        self.assertEqual(list(self.harness.charm._stored.things), [])
        self.harness.update_config({"thing": "foo"})
        self.assertEqual(list(self.harness.charm._stored.things), ["foo"])

    def test_action(self):
        # the harness doesn't (yet!) help much with actions themselves
        action_event = Mock(params={"fail": ""})
        self.harness.charm._on_fortune_action(action_event)

        self.assertTrue(action_event.set_results.called)

    def test_action_fail(self):
        action_event = Mock(params={"fail": "fail this"})
        self.harness.charm._on_fortune_action(action_event)

        self.assertEqual(action_event.fail.call_args, [("fail this",)])

    def test_capsule_pebble_ready(self):
        # Check the initial Pebble plan is empty
        initial_plan = self.harness.get_container_pebble_plan("capsule")
        self.assertEqual(initial_plan.to_yaml(), "{}\n")
        # Expected plan after Pebble ready with default config
        expected_plan = {
            "services": {
                "capsule": {
                    "override": "replace",
                    "summary": "capsule",
                    "command": "/manager",
                    "startup": "enabled",
                    "environment": {"thing": "🎁"},
                }
            },
        }
        # Get the capsule container from the model
        container = self.harness.model.unit.get_container("capsule")
            # Emit the PebbleReadyEvent carrying the capsule container
        self.harness.charm.on.capsule_pebble_ready.emit(container)
        # Get the plan now we've run PebbleReady
        updated_plan = self.harness.get_container_pebble_plan("capsule").to_dict()
        # Check we've got the plan we expected
        self.assertEqual(expected_plan, updated_plan)
        # Check the service was started
        service = self.harness.model.unit.get_container("capsule").get_service("capsule")
        self.assertTrue(service.is_running())
        # Ensure we set an ActiveStatus with no message
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())
