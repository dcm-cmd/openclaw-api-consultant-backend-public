"""Database query script — calls PostgREST API to query business_metrics table."""
import urllib.request
import json
import sys

API_BASE = "http://db-api:3000"


def query(metric=None, category=None, limit=20):
    params = []
    if metric:
        params.append(f"metric_name=eq.{metric}")
    if category:
        params.append(f"category=eq.{category}")
    if limit:
        params.append(f"limit={limit}")
    params.append("order=period.desc")
    url = f"{API_BASE}/business_metrics?{'&'.join(params)}"
    try:
        r = urllib.request.urlopen(url, timeout=10)
        return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("metric", nargs="?", help="metric_name filter")
    p.add_argument("--category", "-c", help="category filter")
    p.add_argument("--limit", "-n", type=int, default=20)
    args = p.parse_args()
    result = query(args.metric, args.category, args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
