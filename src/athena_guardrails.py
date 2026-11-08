"""Retry-safe, budget-aware Amazon Athena query runner.

The module uses no third-party dependencies for request planning and tests.
`boto3` is imported only when the caller explicitly asks to execute a query.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence


TERMINAL_STATES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED"})


class AthenaClient(Protocol):
    def start_query_execution(self, **kwargs: Any) -> Mapping[str, Any]:
        ...

    def get_query_execution(self, **kwargs: Any) -> Mapping[str, Any]:
        ...

    def stop_query_execution(self, **kwargs: Any) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True)
class GuardrailConfig:
    workgroup: str
    database: str
    output_location: str
    catalog: str = "AwsDataCatalog"
    soft_budget_bytes: int = 256 * 1024 * 1024
    result_reuse_minutes: int = 30
    poll_seconds: float = 1.0
    max_poll_attempts: int = 3600

    def __post_init__(self) -> None:
        if not self.workgroup.strip():
            raise ValueError("workgroup must not be empty")
        if not self.database.strip():
            raise ValueError("database must not be empty")
        if not self.output_location.startswith("s3://"):
            raise ValueError("output_location must be an s3:// URI")
        if self.soft_budget_bytes <= 0:
            raise ValueError("soft_budget_bytes must be positive")
        if not 0 <= self.result_reuse_minutes <= 10_080:
            raise ValueError("result_reuse_minutes must be between 0 and 10080")
        if self.poll_seconds < 0:
            raise ValueError("poll_seconds must not be negative")
        if self.max_poll_attempts <= 0:
            raise ValueError("max_poll_attempts must be positive")


@dataclass(frozen=True)
class QueryOutcome:
    query_execution_id: str
    state: str
    data_scanned_bytes: int
    reused_previous_result: bool
    cancellation_requested: bool
    state_change_reason: str | None = None


def _request_token(
    query: str,
    config: GuardrailConfig,
    execution_parameters: Sequence[str],
    request_key: str,
) -> str:
    """Build a stable token for the same logical request.

    Athena requires 32-128 characters. A SHA-256 hex digest is 64 characters.
    """

    identity = {
        "query": query.strip(),
        "catalog": config.catalog,
        "database": config.database,
        "workgroup": config.workgroup,
        "output_location": config.output_location,
        "execution_parameters": list(execution_parameters),
        "request_key": request_key,
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_start_request(
    query: str,
    config: GuardrailConfig,
    execution_parameters: Sequence[str] = (),
    request_key: str | None = None,
) -> dict[str, Any]:
    """Return arguments for Athena's StartQueryExecution API."""

    if not query.strip():
        raise ValueError("query must not be empty")
    effective_request_key = request_key or uuid.uuid4().hex

    request: dict[str, Any] = {
        "QueryString": query.strip(),
        "ClientRequestToken": _request_token(
            query,
            config,
            execution_parameters,
            effective_request_key,
        ),
        "QueryExecutionContext": {
            "Catalog": config.catalog,
            "Database": config.database,
        },
        "ResultConfiguration": {
            "OutputLocation": config.output_location,
        },
        "ResultReuseConfiguration": {
            "ResultReuseByAgeConfiguration": {
                "Enabled": config.result_reuse_minutes > 0,
                "MaxAgeInMinutes": config.result_reuse_minutes,
            }
        },
        "WorkGroup": config.workgroup,
    }
    if execution_parameters:
        request["ExecutionParameters"] = list(execution_parameters)
    return request


def run_query(
    client: AthenaClient,
    query: str,
    config: GuardrailConfig,
    execution_parameters: Sequence[str] = (),
    request_key: str | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> QueryOutcome:
    """Execute and monitor a query with best-effort soft-budget cancellation."""

    start_response = client.start_query_execution(
        **build_start_request(
            query,
            config,
            execution_parameters,
            request_key=request_key,
        )
    )
    query_execution_id = str(start_response["QueryExecutionId"])
    cancellation_requested = False

    for _ in range(config.max_poll_attempts):
        response = client.get_query_execution(
            QueryExecutionId=query_execution_id
        )
        execution = response["QueryExecution"]
        status = execution["Status"]
        statistics = execution.get("Statistics", {})
        state = str(status["State"])
        data_scanned = int(statistics.get("DataScannedInBytes", 0))

        if (
            state not in TERMINAL_STATES
            and data_scanned > config.soft_budget_bytes
            and not cancellation_requested
        ):
            client.stop_query_execution(
                QueryExecutionId=query_execution_id
            )
            cancellation_requested = True

        if state in TERMINAL_STATES:
            reuse_info = statistics.get("ResultReuseInformation", {})
            return QueryOutcome(
                query_execution_id=query_execution_id,
                state=state,
                data_scanned_bytes=data_scanned,
                reused_previous_result=bool(
                    reuse_info.get("ReusedPreviousResult", False)
                ),
                cancellation_requested=cancellation_requested,
                state_change_reason=status.get("StateChangeReason"),
            )

        sleep(config.poll_seconds)

    raise TimeoutError(
        f"Query {query_execution_id} did not reach a terminal state after "
        f"{config.max_poll_attempts} polls"
    )


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan or run a guarded Amazon Athena query."
    )
    parser.add_argument("--query-file", required=True, type=Path)
    parser.add_argument("--workgroup", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--catalog", default="AwsDataCatalog")
    parser.add_argument("--output-location", required=True)
    parser.add_argument("--soft-budget-mb", type=int, default=256)
    parser.add_argument("--result-reuse-minutes", type=int, default=30)
    parser.add_argument(
        "--request-key",
        help=(
            "Stable identifier for one logical submission. Reuse it when "
            "recovering the same run; omit it for a new intentional run."
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Contact AWS. Without this flag, only print the request plan.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    query = args.query_file.read_text(encoding="utf-8")
    config = GuardrailConfig(
        workgroup=args.workgroup,
        database=args.database,
        catalog=args.catalog,
        output_location=args.output_location,
        soft_budget_bytes=args.soft_budget_mb * 1024 * 1024,
        result_reuse_minutes=args.result_reuse_minutes,
    )

    if not args.execute:
        print(
            json.dumps(
                build_start_request(
                    query,
                    config,
                    request_key=args.request_key,
                ),
                indent=2,
            )
        )
        return 0

    try:
        import boto3
    except ImportError:
        print(
            "Execution requires boto3. Install it with: "
            "python3 -m pip install boto3",
            file=sys.stderr,
        )
        return 2

    client = boto3.client("athena")
    outcome = run_query(
        client,
        query,
        config,
        request_key=args.request_key,
    )
    print(json.dumps(outcome.__dict__, indent=2))
    return 0 if outcome.state == "SUCCEEDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

