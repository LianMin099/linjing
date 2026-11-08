"""Prepare a standalone local pilot database and start the query page."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from demo_web import start_server
from import_places import import_dataset, validate_dataset
from linjing_db import connect


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description='Initialize and run the Linjing local pilot.')
    parser.add_argument('--db', type=Path, default=root / 'data' / 'pilot.sqlite')
    parser.add_argument('--port', type=int, default=0, help='Loopback port. Default: choose a free port.')
    parser.add_argument('--open-browser', action='store_true')
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error('--port must be between 0 and 65535')
    try:
        dataset = json.loads((root / 'samples' / 'pilot_osm.json').read_text(encoding='utf-8'))
        metadata, rows = validate_dataset(dataset)
        database = args.db.resolve()
        database.parent.mkdir(parents=True, exist_ok=True)
        with closing(connect(str(database))) as db:
            added = import_dataset(db, metadata, rows)
        print('Samples: {} added, {} already present.'.format(added, len(rows) - added), flush=True)
        start_server(database, args.open_browser, args.port)
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, 'Unable to start Linjing: {}\n'.format(error))


if __name__ == '__main__':
    main()
