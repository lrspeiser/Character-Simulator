import os
import sys
import json
from typing import List

import requests

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


API_URL = "https://api.elevenlabs.io/v2/voices"


def run_search_tests(queries: List[str]) -> None:
    if load_dotenv is not None:
        load_dotenv()

    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        print("ERROR: ELEVENLABS_API_KEY is not set in the environment or .env")
        sys.exit(1)

    headers = {"xi-api-key": api_key}

    results = []

    for q in queries:
        params = {"search": q, "page_size": 5}
        try:
            resp = requests.get(API_URL, headers=headers, params=params, timeout=20)
            status = resp.status_code
            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text}
        except Exception as e:
            results.append({
                "query": q,
                "error": str(e),
            })
            continue

        voices = (data or {}).get("voices", []) if isinstance(data, dict) else []
        summary = []
        for v in voices:
            summary.append({
                "voice_id": v.get("voice_id"),
                "name": v.get("name"),
                "description": v.get("description"),
                "labels": v.get("labels"),
            })

        results.append({
            "query": q,
            "status": status,
            "count": len(voices),
            "voices": summary,
        })

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    # A mix of short and detailed queries to see how sensitive search is
    test_queries = [
        "male",
        "female",
        "young male",
        "young female",
        "older male",
        "older female",
        "gravelly male detective",
        "calm female scientist",
        "energetic male hacker",
        "robotic",
        "child male",
        "child female",
        "neutral narrator",
        "warm narrator female",
        "gritty narrator male",
    ]
    run_search_tests(test_queries)
