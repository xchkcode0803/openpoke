"""Explicit catalog maintenance. Stop application writers before export/rebuild."""
import argparse
import json
import shutil
from pathlib import Path
from .catalog import legacy_slug
from .roster import get_agent_roster
from .log_store import get_execution_agent_logs


def export_legacy(roster, logs, destination):
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Export destination must not already exist')
    names = roster.get_agents()
    slugs = [legacy_slug(name) for name in names]
    if len(set(slugs)) != len(slugs):
        raise ValueError('Legacy format cannot distinguish colliding names; reconcile them before rollback')
    destination.mkdir(parents=True)
    roster.export_json(destination / 'roster.json')
    for name, slug in zip(names, slugs):
        path = logs._log_path(name)
        if path.exists():
            shutil.copy2(path, destination / f'{slug}.log')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['status', 'rebuild', 'export'])
    parser.add_argument('--destination')
    args = parser.parse_args()
    roster, logs = get_agent_roster(), get_execution_agent_logs()
    if args.operation == 'rebuild':
        logs.rebuild_index()
    elif args.operation == 'export':
        if not args.destination:
            parser.error('export requires --destination')
        export_legacy(roster, logs, args.destination)
    else:
        with roster.catalog.connect() as db:
            print(json.dumps({'agents': roster.count(), 'metadata': dict(db.execute('SELECT key,value FROM metadata')),
                              'ambiguous_histories': [row[0] for row in db.execute('SELECT name FROM journals WHERE ambiguous=1')]}, indent=2))


if __name__ == '__main__':
    main()
