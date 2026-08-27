"""Minimal A2A JSON-RPC caller for deployment verification."""

from __future__ import annotations

import argparse
import json
import uuid
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def main() -> int:
    parser = argparse.ArgumentParser(description="Invoke an A2A agent")
    parser.add_argument("url", help="A2A base URL")
    parser.add_argument("message", help="User message")
    parser.add_argument("--bearer-token")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": args.message}],
                "messageId": str(uuid.uuid4()),
            }
        },
    }
    headers = {"Content-Type": "application/json"}
    if args.bearer_token:
        headers["Authorization"] = f"Bearer {args.bearer_token}"
    request = Request(
        urljoin(args.url.rstrip("/") + "/", "./"),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=args.timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

