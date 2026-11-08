from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from athena_guardrails import (  # noqa: E402
    GuardrailConfig,
    build_start_request,
    run_query,
)


class FakeAthenaClient:
    def __init__(self, executions: list[dict[str, Any]]) -> None:
        self.executions = iter(executions)
        self.start_requests: list[dict[str, Any]] = []
        self.stop_requests: list[dict[str, Any]] = []

    def start_query_execution(self, **kwargs: Any) -> dict[str, str]:
        self.start_requests.append(kwargs)
        return {"QueryExecutionId": "query-123"}

    def get_query_execution(self, **kwargs: Any) -> dict[str, Any]:
        return {"QueryExecution": next(self.executions)}

    def stop_query_execution(self, **kwargs: Any) -> dict[str, Any]:
        self.stop_requests.append(kwargs)
        return {}


def config(**overrides: Any) -> GuardrailConfig:
    values = {
        "workgroup": "analytics-guarded",
        "database": "analytics",
        "output_location": "s3://example-results/results/",
        "poll_seconds": 0,
    }
    values.update(overrides)
    return GuardrailConfig(**values)


class BuildStartRequestTests(unittest.TestCase):
    def test_request_enables_result_reuse_and_retry_token(self) -> None:
        request = build_start_request(
            "SELECT 1",
            config(),
            request_key="scheduled-run-123",
        )

        self.assertEqual(request["WorkGroup"], "analytics-guarded")
        self.assertEqual(len(request["ClientRequestToken"]), 64)
        self.assertEqual(
            request["ResultReuseConfiguration"],
            {
                "ResultReuseByAgeConfiguration": {
                    "Enabled": True,
                    "MaxAgeInMinutes": 30,
                }
            },
        )

    def test_same_logical_request_gets_same_token(self) -> None:
        first = build_start_request(
            " SELECT 1\n",
            config(),
            request_key="scheduled-run-123",
        )
        second = build_start_request(
            "SELECT 1",
            config(),
            request_key="scheduled-run-123",
        )
        self.assertEqual(
            first["ClientRequestToken"],
            second["ClientRequestToken"],
        )

    def test_context_change_gets_a_different_token(self) -> None:
        first = build_start_request(
            "SELECT 1",
            config(database="analytics"),
            request_key="scheduled-run-123",
        )
        second = build_start_request(
            "SELECT 1",
            config(database="finance"),
            request_key="scheduled-run-123",
        )
        self.assertNotEqual(
            first["ClientRequestToken"],
            second["ClientRequestToken"],
        )

    def test_new_intentional_run_gets_a_different_token(self) -> None:
        first = build_start_request(
            "SELECT 1",
            config(),
            request_key="scheduled-run-123",
        )
        second = build_start_request(
            "SELECT 1",
            config(),
            request_key="scheduled-run-124",
        )
        self.assertNotEqual(
            first["ClientRequestToken"],
            second["ClientRequestToken"],
        )

    def test_rejects_non_s3_result_location(self) -> None:
        with self.assertRaisesRegex(ValueError, "s3://"):
            config(output_location="/tmp/results")


class RunQueryTests(unittest.TestCase):
    def test_returns_success_and_reuse_metadata(self) -> None:
        client = FakeAthenaClient(
            [
                {
                    "Status": {"State": "RUNNING"},
                    "Statistics": {"DataScannedInBytes": 1024},
                },
                {
                    "Status": {"State": "SUCCEEDED"},
                    "Statistics": {
                        "DataScannedInBytes": 1024,
                        "ResultReuseInformation": {
                            "ReusedPreviousResult": True
                        },
                    },
                },
            ]
        )

        outcome = run_query(client, "SELECT 1", config(), sleep=lambda _: None)

        self.assertEqual(outcome.state, "SUCCEEDED")
        self.assertTrue(outcome.reused_previous_result)
        self.assertFalse(outcome.cancellation_requested)
        self.assertEqual(client.stop_requests, [])

    def test_requests_cancellation_once_after_soft_budget(self) -> None:
        client = FakeAthenaClient(
            [
                {
                    "Status": {"State": "RUNNING"},
                    "Statistics": {"DataScannedInBytes": 101},
                },
                {
                    "Status": {"State": "RUNNING"},
                    "Statistics": {"DataScannedInBytes": 150},
                },
                {
                    "Status": {
                        "State": "CANCELLED",
                        "StateChangeReason": "User cancelled",
                    },
                    "Statistics": {"DataScannedInBytes": 150},
                },
            ]
        )

        outcome = run_query(
            client,
            "SELECT * FROM orders",
            config(soft_budget_bytes=100),
            sleep=lambda _: None,
        )

        self.assertEqual(outcome.state, "CANCELLED")
        self.assertTrue(outcome.cancellation_requested)
        self.assertEqual(
            client.stop_requests,
            [{"QueryExecutionId": "query-123"}],
        )

    def test_times_out_when_query_never_finishes(self) -> None:
        client = FakeAthenaClient(
            [
                {
                    "Status": {"State": "RUNNING"},
                    "Statistics": {"DataScannedInBytes": 1},
                }
            ]
        )

        with self.assertRaises(TimeoutError):
            run_query(
                client,
                "SELECT 1",
                config(max_poll_attempts=1),
                sleep=lambda _: None,
            )


if __name__ == "__main__":
    unittest.main()

