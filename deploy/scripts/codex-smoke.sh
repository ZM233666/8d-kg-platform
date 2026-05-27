#!/usr/bin/env bash
# Codex 服务冒烟测试（在宿主机执行）
set -euo pipefail

BASE_URL="${CODEX_SMOKE_URL:-http://127.0.0.1:8787}"

echo "==> GET ${BASE_URL}/health"
curl -fsS "${BASE_URL}/health"
echo ""

echo "==> POST ${BASE_URL}/extract (minimal payload)"
# 最小请求：仅验证 HTTP 与 JSON 通路；完整抽取需有效 LLM/Codex 鉴权
curl -fsS -X POST "${BASE_URL}/extract" \
  -H "Content-Type: application/json" \
  -d '{
    "system_prompt": "你是 JSON 抽取器，只输出 JSON。",
    "user_prompt": "输出 {\"report\": null, \"event\": null, \"failure_modes\": [], \"causes\": [], \"actions\": [], \"product_instances\": [], \"part_serials\": [], \"organizations\": [], \"persons\": [], \"failure_products\": [], \"failure_product_mentions\": [], \"relationships\": [], \"chunks\": [], \"stats\": {}}",
    "response_model_name": "ExtractionResult",
    "response_schema": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "report": {"anyOf": [{"type": "null"}, {"type": "object"}]},
        "event": {"anyOf": [{"type": "null"}, {"type": "object"}]},
        "failure_modes": {"type": "array"},
        "causes": {"type": "array"},
        "actions": {"type": "array"},
        "product_instances": {"type": "array"},
        "part_serials": {"type": "array"},
        "organizations": {"type": "array"},
        "persons": {"type": "array"},
        "failure_products": {"type": "array"},
        "failure_product_mentions": {"type": "array"},
        "relationships": {"type": "array"},
        "chunks": {"type": "array"},
        "stats": {"type": "object"}
      },
      "required": [
        "report", "event", "failure_modes", "causes", "actions",
        "product_instances", "part_serials", "organizations", "persons",
        "failure_products", "failure_product_mentions", "relationships",
        "chunks", "stats"
      ]
    },
    "max_tokens": 512,
    "temperature": 0.1,
    "request_context": {
      "skill_name": "8d-report-extraction-core",
      "skill_version": "draft",
      "route_name": "smoke_test"
    }
  }' | head -c 2000

echo ""
echo "==> smoke finished (check HTTP status and response body above)"
