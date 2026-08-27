"""Export ARMS traces to local JSON files.

The script uses SearchTracesByPage when the installed SDK exposes it, falls
back to SearchTraces otherwise, and then downloads every trace through
GetTrace. Credentials are read only from standard environment variables.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alibabacloud_arms20190808 import models as arms_models
from alibabacloud_arms20190808.client import Client as ArmsClient
from alibabacloud_tea_openapi import models as open_api_models


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def _to_map(value: Any) -> Any:
    if hasattr(value, "to_map"):
        return value.to_map()
    if isinstance(value, dict):
        return {key: _to_map(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_map(item) for item in value]
    return value


def _find_values(node: Any, key_name: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key.lower().replace("_", "") == key_name.lower().replace("_", ""):
                found.append(value)
            found.extend(_find_values(value, key_name))
    elif isinstance(node, list):
        for value in node:
            found.extend(_find_values(value, key_name))
    return found


def _new_request(class_name: str, **fields: Any):
    request_class = getattr(arms_models, class_name)
    request = request_class()
    for name, value in fields.items():
        if value is not None:
            setattr(request, name, value)
    return request


def _call_with_retry(operation, request, attempts: int = 4):
    for attempt in range(1, attempts + 1):
        try:
            return operation(request)
        except Exception:
            if attempt == attempts:
                raise
            time.sleep(min(2 ** (attempt - 1), 8))
    raise AssertionError("unreachable")


def build_client(region: str, endpoint: str | None) -> ArmsClient:
    config = open_api_models.Config(
        access_key_id=_required_env("ALIBABA_CLOUD_ACCESS_KEY_ID"),
        access_key_secret=_required_env("ALIBABA_CLOUD_ACCESS_KEY_SECRET"),
        security_token=os.getenv("ALIBABA_CLOUD_SECURITY_TOKEN"),
        region_id=region,
        endpoint=endpoint or f"arms.{region}.aliyuncs.com",
    )
    return ArmsClient(config)


def search_trace_ids(
    client: ArmsClient,
    *,
    region: str,
    start_ms: int,
    end_ms: int,
    service_name: str | None,
    max_pages: int,
    page_size: int,
) -> list[str]:
    paged = hasattr(client, "search_traces_by_page") and hasattr(
        arms_models, "SearchTracesByPageRequest"
    )
    operation = client.search_traces_by_page if paged else client.search_traces
    request_name = "SearchTracesByPageRequest" if paged else "SearchTracesRequest"
    trace_ids: list[str] = []
    seen: set[str] = set()

    for page_number in range(1, max_pages + 1):
        request = _new_request(
            request_name,
            region_id=region,
            start_time=start_ms,
            end_time=end_ms,
            service_name=service_name,
            page_number=page_number,
            page_size=page_size,
        )
        payload = _to_map(_call_with_retry(operation, request).body)
        page_ids = [str(value) for value in _find_values(payload, "TraceID") if value]
        new_ids = [trace_id for trace_id in page_ids if trace_id not in seen]
        for trace_id in new_ids:
            seen.add(trace_id)
            trace_ids.append(trace_id)
        if not paged or not new_ids or len(set(page_ids)) < page_size:
            break
    return trace_ids


def download_trace(
    client: ArmsClient,
    *,
    trace_id: str,
    region: str,
    start_ms: int,
    end_ms: int,
    page_size: int,
    max_pages: int,
) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    span_ids_seen: set[str] = set()
    for page_number in range(1, max_pages + 1):
        request = _new_request(
            "GetTraceRequest",
            trace_id=trace_id,
            region_id=region,
            start_time=start_ms,
            end_time=end_ms,
            page_number=page_number,
            page_size=page_size,
        )
        payload = _to_map(_call_with_retry(client.get_trace, request).body)
        pages.append(payload)
        page_span_ids = {
            str(value) for value in _find_values(payload, "SpanId") if value is not None
        }
        new_span_ids = page_span_ids - span_ids_seen
        span_ids_seen.update(page_span_ids)
        if not new_span_ids or len(page_span_ids) < page_size:
            break
    return {
        "trace_id": trace_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "span_count": len(span_ids_seen),
        "pages": pages,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export ARMS traces to local JSON")
    parser.add_argument("--region", default=os.getenv("AGENTRUN_REGION", "cn-hangzhou"))
    parser.add_argument("--service-name", help="ARMS application/service name")
    parser.add_argument(
        "--trace-id",
        action="append",
        help="Download an exact Trace ID; repeat to download multiple traces",
    )
    parser.add_argument("--minutes", type=int, default=60, help="Lookback window")
    parser.add_argument("--start-ms", type=int, help="Explicit start epoch milliseconds")
    parser.add_argument("--end-ms", type=int, help="Explicit end epoch milliseconds")
    parser.add_argument("--endpoint", help="Override ARMS OpenAPI endpoint")
    parser.add_argument("--output", type=Path, default=Path("trace-export"))
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=100)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.page_size <= 100:
        raise ValueError("--page-size must be between 1 and 100")
    end_ms = args.end_ms or int(time.time() * 1000)
    start_ms = args.start_ms or end_ms - args.minutes * 60 * 1000
    if start_ms >= end_ms:
        raise ValueError("start time must be earlier than end time")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    client = build_client(args.region, args.endpoint)
    if args.trace_id:
        invalid = [value for value in args.trace_id if not re.fullmatch(r"[0-9a-fA-F]{32}", value)]
        if invalid:
            raise ValueError("--trace-id must be a 32-character hexadecimal value")
        trace_ids = list(dict.fromkeys(value.lower() for value in args.trace_id))
    else:
        trace_ids = search_trace_ids(
            client,
            region=args.region,
            start_ms=start_ms,
            end_ms=end_ms,
            service_name=args.service_name,
            max_pages=args.max_pages,
            page_size=args.page_size,
        )

    index: list[dict[str, Any]] = []
    for position, trace_id in enumerate(trace_ids, 1):
        print(f"[{position}/{len(trace_ids)}] downloading {trace_id}", file=sys.stderr)
        trace = download_trace(
            client,
            trace_id=trace_id,
            region=args.region,
            start_ms=start_ms,
            end_ms=end_ms,
            page_size=args.page_size,
            max_pages=args.max_pages,
        )
        target = output / f"{trace_id}.json"
        target.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
        index.append(
            {
                "trace_id": trace_id,
                "span_count": trace["span_count"],
                "file": target.name,
            }
        )

    summary = {
        "region": args.region,
        "service_name": args.service_name,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "trace_count": len(index),
        "traces": index,
    }
    (output / "index.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Exported {len(index)} trace(s) to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
