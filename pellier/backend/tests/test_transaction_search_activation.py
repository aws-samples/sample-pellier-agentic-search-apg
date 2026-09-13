"""Fresh accounts must survive delayed X-Ray destination activation."""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def activation(monkeypatch):
    path = Path(__file__).resolve().parents[3] / "scripts/provision_agentcore_end_to_end.py"
    spec = importlib.util.spec_from_file_location("transaction_search_provisioner", path)
    assert spec and spec.loader
    provisioner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(provisioner)

    class Clock:
        now = 0.0
        sleeps = []

        def monotonic(self):
            return self.now

        def sleep(self, seconds):
            self.sleeps.append(seconds)
            self.now += seconds

    clock = Clock()

    class Logs:
        def describe_resource_policies(self, **kwargs):
            return {"resourcePolicies": []}

        def put_resource_policy(self, **kwargs):
            pass

    class XRay:
        destination = "CloudWatchLogs"
        active_after = 600
        stuck_response = None
        updates = []

        def get_trace_segment_destination(self):
            if self.stuck_response:
                return dict(self.stuck_response)
            return {
                "Destination": self.destination,
                "Status": "ACTIVE" if clock.now >= self.active_after else "PENDING",
            }

        def update_trace_segment_destination(self, *, Destination):
            self.updates.append(Destination)
            self.destination = Destination

    xray = XRay()
    monkeypatch.setattr(provisioner.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(provisioner.time, "sleep", clock.sleep)
    monkeypatch.setattr(
        provisioner.boto3, "client",
        lambda service, **kwargs: {"logs": Logs(), "xray": xray}[service],
    )
    return provisioner, clock, xray


def configure(provisioner, checkpoints):
    return provisioner._configure_transaction_search(
        region="us-east-1",
        account_id="123456789012",
        partition="aws",
        on_cleanup_state=lambda receipt: checkpoints.append(dict(receipt)),
    )


@pytest.mark.parametrize("prior_destination", ["XRay", "CloudWatchLogs"])
def test_first_account_activation_can_take_ten_minutes(
    activation, capsys, prior_destination
):
    provisioner, clock, xray = activation
    xray.destination = prior_destination
    checkpoints = []

    receipt = configure(provisioner, checkpoints)

    assert clock.now == 600
    assert receipt["destination"] == "CloudWatchLogs"
    assert receipt["status"] == "ACTIVE"
    assert xray.updates == (["CloudWatchLogs"] if prior_destination == "XRay" else [])
    assert any(
        item.get("status") == "PENDING" and item.get("elapsed_seconds", 0) >= 300
        for item in checkpoints
    )
    output = capsys.readouterr().out
    assert "status=PENDING" in output
    assert "elapsed=300s" in output
    assert "Transaction Search ACTIVE after 600s" in output


@pytest.mark.parametrize(
    "stuck_response",
    [
        {"Destination": "CloudWatchLogs", "Status": "PENDING"},
        {"Destination": "XRay", "Status": "ACTIVE"},
    ],
)
def test_activation_timeout_fails_closed_with_last_observed_state(
    activation, capsys, stuck_response
):
    provisioner, clock, xray = activation
    xray.stuck_response = stuck_response
    checkpoints = []

    with pytest.raises(RuntimeError, match="CloudWatchLogs/ACTIVE within 900s"):
        configure(provisioner, checkpoints)

    assert clock.now == 900
    assert checkpoints[-1]["observed_destination"] == stuck_response["Destination"]
    assert checkpoints[-1]["observed_status"] == stuck_response["Status"]
    assert checkpoints[-1]["status"] != "ACTIVE"
    assert checkpoints[-1]["elapsed_seconds"] == 900
    assert checkpoints[-1]["timeout_seconds"] == 900
    assert f"status={stuck_response['Status']}" in capsys.readouterr().err


def test_active_destination_does_not_wait_or_restart_activation(activation):
    provisioner, clock, xray = activation
    xray.active_after = 0

    receipt = configure(provisioner, [])

    assert receipt["status"] == "ACTIVE"
    assert clock.now == 0
    assert clock.sleeps == []
    assert xray.updates == []
