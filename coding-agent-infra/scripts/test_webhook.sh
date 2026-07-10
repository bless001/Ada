#!/usr/bin/env bash
set -euo pipefail

curl -X POST "http://localhost:8090/webhooks/openproject" \
  -H "Content-Type: application/json" \
  -d '{
    "event_name": "work_package:updated",
    "_embedded": {
      "workPackage": {
        "id": 1
      }
    },
    "comment": {
      "raw": "Test webhook from local script."
    }
  }'
