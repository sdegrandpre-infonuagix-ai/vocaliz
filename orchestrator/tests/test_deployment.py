"""The deployable artefacts: container image, hand-written ECS task definition, one pipeline.

These are checked in code rather than left to a deploy that fails in six months, because
the task definition and the settings object have to agree on names — and nothing else
would notice when they stop agreeing.
"""
import json
from pathlib import Path

import pytest
import yaml

from src.config import REQUIRED_SECRETS, Settings
from src.main import HEALTH_PATH, READINESS_PATH

ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ORCHESTRATOR_ROOT.parent

DOCKERFILE = ORCHESTRATOR_ROOT / "Dockerfile"
TASK_DEFINITION = ORCHESTRATOR_ROOT / "ecs" / "task-definition.json"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"


@pytest.fixture(scope="module")
def task_definition():
    return json.loads(TASK_DEFINITION.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def container(task_definition):
    (only,) = task_definition["containerDefinitions"]
    return only


def test_the_project_builds_a_container_image():
    assert DOCKERFILE.is_file()
    assert "uvicorn" in DOCKERFILE.read_text(encoding="utf-8")


def test_the_task_definition_targets_fargate(task_definition):
    assert task_definition["requiresCompatibilities"] == ["FARGATE"]
    assert task_definition["networkMode"] == "awsvpc"
    assert task_definition["family"] == "salon-orchestrator"


def test_the_task_definition_is_hand_written_json_not_a_cdk_output(task_definition):
    """No IaC tool for the MVP: this file is the source, not a synthesised artefact."""
    assert "cdk.out" not in str(TASK_DEFINITION)
    assert "Resources" not in task_definition  # a CloudFormation template, not a task def


def test_the_container_exposes_the_port_the_settings_default_to(container):
    port = Settings.model_fields["port"].default

    assert [m["containerPort"] for m in container["portMappings"]] == [port]
    assert container["environment"] == sorted(
        container["environment"], key=lambda entry: entry["name"]
    )


def test_secrets_reach_the_container_from_secrets_manager(container):
    names = {entry["name"] for entry in container["environment"]}

    assert "ORCHESTRATOR_SECRET_ARN" in names


def test_no_secret_is_written_in_clear_in_the_task_definition(container):
    """The task definition is committed to git — a credential in it is a leaked credential."""
    plaintext = {entry["name"] for entry in container["environment"]}

    assert plaintext.isdisjoint(REQUIRED_SECRETS)


def test_the_health_check_uses_liveness_not_readiness(container):
    """A draining task answers 503 on readiness; probing that would kill it mid-Salon."""
    command = " ".join(container["healthCheck"]["command"])

    assert HEALTH_PATH in command
    assert READINESS_PATH not in command


def test_the_stop_timeout_leaves_room_for_the_drain(container):
    assert container["stopTimeout"] >= Settings.model_fields["drain_timeout_seconds"].default


def test_logs_go_to_cloudwatch(container):
    assert container["logConfiguration"]["logDriver"] == "awslogs"


def test_the_orchestrator_is_built_by_the_existing_pipeline():
    """One pipeline for every component — no parallel chain for the orchestrator."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))

    assert "orchestrator" in workflow["jobs"]
    steps = json.dumps(workflow["jobs"]["orchestrator"])
    assert "ecs/task-definition.json" in steps
