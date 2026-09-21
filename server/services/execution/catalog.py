"""SQLite roster and rebuildable ownership index; journals remain authoritative."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata


def normalize(text):
    return ' '.join(re.sub(r'[\W_]+', ' ', unicodedata.normalize('NFKC', text).casefold()).split())


def legacy_slug(name):
    return re.sub('-+', '-', ''.join(c.lower() if c.isalnum() else '-' for c in name.strip()).strip('-')) or 'agent'


def journal_filename(name):
    """Stable journal path without legacy slug collisions."""
    return "agent-" + hashlib.sha256(name.encode()).hexdigest() + ".log"


class Catalog:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'agents.sqlite3'
        self.legacy = self.directory / 'roster.json'
        self.backup = self.directory / 'roster.legacy.json'
        if not self.path.exists() and self.backup.exists():
            raise RuntimeError('Catalog missing beside migration backup; restore explicitly instead of creating an empty roster')
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS agents(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE COLLATE BINARY,
                    normalized TEXT NOT NULL, slug TEXT NOT NULL, words INTEGER NOT NULL, journal_key TEXT NOT NULL,
                    initial_assignment TEXT, latest_assignment TEXT,
                    initial_truncated INTEGER NOT NULL DEFAULT 0, latest_truncated INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS agent_normalized ON agents(normalized);
                CREATE INDEX IF NOT EXISTS agent_slug ON agents(slug);
                CREATE INDEX IF NOT EXISTS agent_words ON agents(words);
                CREATE INDEX IF NOT EXISTS agent_journal ON agents(journal_key);
                CREATE TABLE IF NOT EXISTS journals(name TEXT PRIMARY KEY, path TEXT UNIQUE NOT NULL,
                    offset INTEGER NOT NULL DEFAULT 0, identity TEXT, dirty INTEGER NOT NULL DEFAULT 0,
                    ambiguous INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS pending_journals ON journals(dirty) WHERE dirty=1;
                CREATE TABLE IF NOT EXISTS entries(id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                    position INTEGER NOT NULL, kind TEXT NOT NULL, timestamp TEXT NOT NULL, text TEXT NOT NULL,
                    UNIQUE(name,position));
                CREATE INDEX IF NOT EXISTS entry_owner ON entries(name,position DESC);
                CREATE INDEX IF NOT EXISTS assignment_owner ON entries(name,position) WHERE kind='agent_request';
                CREATE VIRTUAL TABLE IF NOT EXISTS profiles USING fts5(name, initial_assignment, latest_assignment,
                    tokenize='porter unicode61 remove_diacritics 2');
                CREATE VIRTUAL TABLE IF NOT EXISTS history_search USING fts5(text,normalized_text, tokenize='porter unicode61 remove_diacritics 2');
                CREATE TRIGGER IF NOT EXISTS agent_insert AFTER INSERT ON agents WHEN NOT EXISTS(SELECT 1 FROM metadata WHERE key='bulk_mode') BEGIN
                    INSERT INTO profiles(rowid,name,initial_assignment,latest_assignment)
                    VALUES(new.id,new.normalized,new.initial_assignment,new.latest_assignment); END;
                CREATE TRIGGER IF NOT EXISTS agent_update AFTER UPDATE ON agents WHEN NOT EXISTS(SELECT 1 FROM metadata WHERE key='bulk_mode') BEGIN
                    DELETE FROM profiles WHERE rowid=old.id;
                    INSERT INTO profiles(rowid,name,initial_assignment,latest_assignment)
                    VALUES(new.id,new.normalized,new.initial_assignment,new.latest_assignment); END;
                CREATE TRIGGER IF NOT EXISTS agent_delete AFTER DELETE ON agents WHEN NOT EXISTS(SELECT 1 FROM metadata WHERE key='bulk_mode') BEGIN
                    DELETE FROM profiles WHERE rowid=old.id; END;
                CREATE TRIGGER IF NOT EXISTS entry_insert AFTER INSERT ON entries BEGIN
                    INSERT INTO history_search(rowid,text,normalized_text) VALUES(new.id,new.text,normalize(new.text)); END;
                CREATE TRIGGER IF NOT EXISTS entry_delete AFTER DELETE ON entries BEGIN
                    DELETE FROM history_search WHERE rowid=old.id; END;
            ''')
            db.execute('BEGIN IMMEDIATE')
            if not db.execute("SELECT 1 FROM metadata WHERE key='initialized'").fetchone():
                names = json.loads(self.legacy.read_text()) if self.legacy.exists() else []
                self._validate_names(names)
                unique = list(dict.fromkeys(names))
                self._bulk_replace(db, unique)
                db.execute("INSERT INTO metadata VALUES('migration_duplicates',?)", (str(len(names)-len(unique)),))
                db.execute("INSERT INTO metadata VALUES('initialized','1')")
                db.execute("INSERT INTO metadata VALUES('count',?)", (str(len(unique)),))
                db.execute("INSERT INTO metadata VALUES('version','1')")
            if db.execute("SELECT value FROM metadata WHERE key='version'").fetchone()[0] != '1':
                raise RuntimeError('Unsupported agent catalog version')
        if self.legacy.exists() and not self.backup.exists():
            self.legacy.rename(self.backup)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.create_function('normalize', 1, normalize, deterministic=True)
        db.execute('PRAGMA cache_size=-32768')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _validate_names(names):
        if not isinstance(names, (list, tuple)) or any(not isinstance(n, str) or not n.strip() for n in names):
            raise ValueError('Roster must be a list of nonempty exact agent names')

    @staticmethod
    def _insert(db, names):
        def rows():
            for name in names:
                normalized = normalize(name)
                yield (name, normalized, legacy_slug(name),
                       len(normalized.split()), journal_filename(name))
        db.executemany('INSERT INTO agents(name,normalized,slug,words,journal_key) VALUES(?,?,?,?,?)', rows())

    def count(self):
        with self.connect() as db:
            return int(db.execute("SELECT value FROM metadata WHERE key='count'").fetchone()[0])

    def contains(self, name):
        if not isinstance(name, str):
            return False
        with self.connect() as db:
            return db.execute('SELECT 1 FROM agents WHERE name=?', (name,)).fetchone() is not None

    def add(self, name):
        self._validate_names([name])
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM agents WHERE name=?', (name,)).fetchone():
                return False
            self._insert(db, [name])
            db.execute("UPDATE metadata SET value=CAST(value AS INTEGER)+1 WHERE key='count'")
            self.refresh_profile(db, name)
        return True

    def replace(self, names):
        self._validate_names(names)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._bulk_replace(db, dict.fromkeys(names))
            db.execute("UPDATE metadata SET value=(SELECT count(*) FROM agents) WHERE key='count'")

    def _bulk_replace(self, db, names):
        # Build FTS in one statement rather than invoking a trigger per document.
        indexes = {'agent_normalized': 'normalized', 'agent_slug': 'slug', 'agent_words': 'words', 'agent_journal': 'journal_key'}
        for name in indexes:
            db.execute(f'DROP INDEX {name}')
        db.execute("INSERT INTO metadata VALUES('bulk_mode','1')")
        db.execute('DELETE FROM agents')
        db.execute('DELETE FROM profiles')
        self._insert(db, names)
        for row in db.execute('SELECT DISTINCT name FROM entries'):
            self.refresh_profile(db, row[0])
        db.execute('INSERT INTO profiles(rowid,name,initial_assignment,latest_assignment) SELECT id,normalized,initial_assignment,latest_assignment FROM agents')
        db.execute("DELETE FROM metadata WHERE key='bulk_mode'")
        for name, column in indexes.items():
            db.execute(f'CREATE INDEX {name} ON agents({column})')

    def names(self, limit=None):
        with self.connect() as db:
            return [row[0] for row in db.execute('SELECT name FROM agents ORDER BY id LIMIT ?', (-1 if limit is None else limit,))]

    def register_journal(self, name):
        filename = journal_filename(name)
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO journals(name,path) VALUES(?,?)', (name, filename))
            return dict(db.execute('SELECT * FROM journals WHERE name=?', (name,)).fetchone())

    def bootstrap_logs(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM metadata WHERE key='logs_bootstrapped'").fetchone():
                return
            for path in self.directory.glob('*.log'):
                owners = list(db.execute('SELECT name FROM agents WHERE slug=? OR journal_key=?', (path.stem,path.name)))
                if len(owners) == 1:
                    db.execute('INSERT OR IGNORE INTO journals(name,path,dirty) VALUES(?,?,1)', (owners[0][0], path.name))
                elif owners:
                    for owner in owners:
                        filename = journal_filename(owner[0])
                        db.execute('INSERT OR IGNORE INTO journals(name,path,ambiguous) VALUES(?,?,1)', (owner[0], filename))
            db.execute("INSERT INTO metadata VALUES('logs_bootstrapped','1')")

    @staticmethod
    def refresh_profile(db, name):
        first = db.execute("SELECT text FROM entries WHERE name=? AND kind='agent_request' ORDER BY position LIMIT 1", (name,)).fetchone()
        last = db.execute("SELECT text FROM entries WHERE name=? AND kind='agent_request' ORDER BY position DESC LIMIT 1", (name,)).fetchone()
        initial, latest = (first[0] if first else None), (last[0] if last else None)
        db.execute('UPDATE agents SET initial_assignment=?,latest_assignment=?,initial_truncated=?,latest_truncated=? WHERE name=?',
                   (initial[:400] if initial else initial, latest[:400] if latest else latest,
                    bool(initial and len(initial)>400), bool(latest and len(latest)>400), name))

    def has_history(self):
        with self.connect() as db:
            return db.execute('SELECT 1 FROM entries JOIN agents USING(name) LIMIT 1').fetchone() is not None
