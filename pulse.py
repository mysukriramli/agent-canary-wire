#!/usr/bin/env python3
"""
Agent Canary Wire - Real-Time AI Gateway & Provider Status Monitor
Runs high-frequency health checks across foundation model providers
to generate instant failover directives for autonomous agent runtimes.
"""

import os
import json
import logging
from datetime import datetime, timezone
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

OUTPUT_JSON = "latest/canary.json"
OUTPUT_LLMS = "latest/llms.txt"

TARGET_PROVIDERS = {
    "openai": "https://status.openai.com/api/v2/summary.json",
    "anthropic": "https://status.anthropic.com/api/v2/summary.json",
    "github_copilot": "https://www.githubstatus.com/api/v2/summary.json",
    "cloudflare": "https://www.cloudflarestatus.com/api/v2/summary.json",
    "huggingface": "https://status.huggingface.co/api/v2/summary.json"
}

def inspect_provider(name: str, url: str) -> dict:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; Agent-Canary-Wire/1.0)"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200:
            return {
                "status": "UNKNOWN",
                "indicator": "minor",
                "description": f"HTTP {res.status_code}",
                "active_incident_count": 1,
                "incidents": []
            }
        
        data = res.json()
        status_info = data.get("status", {})
        indicator = status_info.get("indicator", "none")
        description = status_info.get("description", "Operational")
        
        incidents = data.get("incidents", [])
        active = [
            {"name": inc.get("name"), "impact": inc.get("impact"), "status": inc.get("status")}
            for inc in incidents if inc.get("status") != "resolved"
        ]

        normalized_status = "OPERATIONAL" if indicator in ["none", "operational"] else "DEGRADED"

        return {
            "status": normalized_status,
            "severity": indicator,
            "description": description,
            "active_incident_count": len(active),
            "incidents": active[:2]
        }
    except Exception as e:
        logging.warning(f"Failed to check {name}: {e}")
        return {
            "status": "UNREACHABLE",
            "severity": "critical",
            "description": "Provider health probe timed out.",
            "active_incident_count": 0,
            "incidents": []
        }

def determine_routing(results: dict) -> tuple:
    openai_ok = results.get("openai", {}).get("status") == "OPERATIONAL"
    anthropic_ok = results.get("anthropic", {}).get("status") == "OPERATIONAL"

    if openai_ok and anthropic_ok:
        return "openai", "All primary foundation gateways operational. Route traffic normally."
    elif anthropic_ok and not openai_ok:
        return "anthropic", "FAILOVER ACTIVE: OpenAI is degraded/unreachable. Divert calls to Anthropic Claude."
    elif openai_ok and not anthropic_ok:
        return "openai", "FAILOVER ACTIVE: Anthropic is degraded/unreachable. Divert calls to OpenAI GPT-4o."
    else:
        return "local_fallback", "EMERGENCY: Both major frontier gateways degraded. Route to local or backup provider."

def main():
    logging.info("Starting Agent Canary pulse check...")
    results = {}
    for name, url in TARGET_PROVIDERS.items():
        results[name] = inspect_provider(name, url)

    recommended_llm, directive = determine_routing(results)
    now_iso = datetime.now(timezone.utc).isoformat()

    payload = {
        "metadata": {
            "timestamp_utc": now_iso,
            "schema_version": "1.0.0",
            "check_frequency_minutes": 30
        },
        "routing_directive": {
            "recommended_primary_llm": recommended_llm,
            "action": directive
        },
        "providers": results
    }

    os.makedirs("latest", exist_ok=True)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    llms_text = (
        f"# AI Provider Canary Status ({now_iso})\n"
        f"> Recommended Gateway: `{recommended_llm.upper()}`\n\n"
        f"**Directive:** {directive}\n\n"
        f"- OpenAI: {results['openai']['status']} ({results['openai']['description']})\n"
        f"- Anthropic: {results['anthropic']['status']} ({results['anthropic']['description']})\n"
        f"- GitHub: {results['github_copilot']['status']} ({results['github_copilot']['description']})\n"
        f"- Cloudflare: {results['cloudflare']['status']} ({results['cloudflare']['description']})\n"
        f"- Hugging Face: {results['huggingface']['status']} ({results['huggingface']['description']})\n"
    )

    with open(OUTPUT_LLMS, "w", encoding="utf-8") as f:
        f.write(llms_text)

    logging.info(f"Canary pulse complete. Primary route: {recommended_llm}")

if __name__ == "__main__":
    main()
