"""Opt-in retention: python -m scripts.prune_conversations --days 90 [--apply]."""
import argparse
import asyncio
import json
import os

from backend.app.observability.store import ConversationStore


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--days', type=int, default=int(os.getenv('TRACE_RETENTION_DAYS','0')))
    parser.add_argument('--apply', action='store_true', help='Delete in bounded batches; otherwise report only')
    args = parser.parse_args()
    if args.days < 0:
        parser.error('days must be non-negative; 0 disables retention')
    store = ConversationStore(os.getenv('DATABASE_URL',''))
    try:
        print(json.dumps(await store.prune(args.days, apply=args.apply)))
    finally:
        await store.aclose()


if __name__ == '__main__':
    asyncio.run(main())
