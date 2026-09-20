"""Bounded BM25 retrieval shared by prompt construction and discovery tools."""
import re
from ...services.execution.catalog import normalize

MAX_CANDIDATES = 20
SEARCH_PAGE_SIZE = 10
SEARCH_POOL_SIZE = 100
RECENT_HISTORY_CHAR_LIMIT = 6000
QUERY_TERM_LIMIT = 64


def _query(text):
    # Literal tokens only: model-supplied FTS operators cannot become syntax.
    terms = list(dict.fromkeys(re.findall(r'\w+', normalize(text), re.UNICODE)))[:QUERY_TERM_LIMIT]
    return ' OR '.join('"' + word.replace('"', '""') + '"' for word in terms)


def _mentions(db, text):
    words = normalize(text).split()
    maximum = db.execute('SELECT max(words) FROM agents').fetchone()[0] or 0
    found = {}
    # Text-driven exact lookups. No enumeration of the roster or name trie.
    batch = {}
    for end in range(len(words)):
        for length in range(1, min(maximum, end + 1) + 1):
            batch[' '.join(words[end-length+1:end+1])] = end
            if len(batch) >= 400:
                _lookup_mentions(db, batch, found)
                batch.clear()
    _lookup_mentions(db, batch, found)
    return dict(sorted(found.items(), key=lambda item: (-item[1], item[0]))[:100])


def _lookup_mentions(db, batch, found):
    if batch:
        placeholders = ','.join('?' for _ in batch)
        for row in db.execute(f'SELECT id,normalized FROM agents WHERE normalized IN ({placeholders}) ORDER BY normalized,name LIMIT 100', tuple(batch)):
            found[row['id']] = batch[row['normalized']]
        if len(found) > 100:
            retained = sorted(found.items(), key=lambda item: (-item[1], item[0]))[:100]
            found.clear()
            found.update(retained)


def _hits(db, text, history):
    query = _query(text)
    if not query:
        return []
    if history:
        return list(db.execute('''SELECT a.id,a.name,a.normalized,e.kind,e.timestamp,e.position,e.text,
            snippet(history_search,0,'','',' … ',32) AS excerpt,history_search.rank AS score
            FROM history_search JOIN entries e ON e.id=history_search.rowid JOIN agents a ON a.name=e.name
            WHERE history_search MATCH ? ORDER BY history_search.rank,a.normalized,a.name,e.id LIMIT 100''', (query,)))
    return list(db.execute('''SELECT a.id,a.name,a.normalized,profiles.rank AS score
        FROM profiles JOIN agents a ON a.id=profiles.rowid
        WHERE profiles MATCH ? AND profiles.rank MATCH 'bm25(3.0,1.0,2.0)'
        ORDER BY profiles.rank,a.normalized,a.name LIMIT 100''', (query,)))


def ranked_candidates(catalog, query, history=''):
    scores, evidence, names = {}, {}, {}
    with catalog.connect() as db:
        db.execute('BEGIN')  # One read snapshot across all retrieval streams.
        current_mentions = _mentions(db, query)
        past_mentions = _mentions(db, history)
        exact = {row[0] for row in db.execute('SELECT id FROM agents WHERE normalized=? ORDER BY name LIMIT 100', (normalize(query),))}
        for text, weight in ((query, 3), (history[-RECENT_HISTORY_CHAR_LIMIT:], 1)):
            for is_history in (False, True):
                seen = set()
                for row in _hits(db, text, is_history):
                    identifier = row['id']
                    if identifier in seen:
                        continue
                    seen.add(identifier)
                    names[identifier] = (row['normalized'], row['name'])
                    scores[identifier] = scores.get(identifier, 0) + weight / (60 + len(seen))
                    if is_history and identifier not in evidence:
                        evidence[identifier] = {'type': row['kind'], 'timestamp': row['timestamp'],
                            'source': f"{row['name']}:{row['position']}", 'text': row['excerpt'][:400],
                            'truncated': len(row['text']) > len(row['excerpt'][:400])}
        for identifier in exact | current_mentions.keys() | past_mentions.keys():
            row = db.execute('SELECT normalized,name FROM agents WHERE id=?', (identifier,)).fetchone()
            names[identifier] = (row['normalized'], row['name'])
            scores.setdefault(identifier, 0)
        ranked = sorted(scores, key=lambda identifier: (
            -int(identifier in exact), -int(identifier in current_mentions),
            -int(identifier in past_mentions), -scores[identifier],
            -past_mentions.get(identifier, -1), *names[identifier], identifier))[:SEARCH_POOL_SIZE]
        return [_profile(db, identifier, evidence.get(identifier)) for identifier in ranked]


def _profile(db, identifier, evidence=None):
    row = db.execute('SELECT * FROM agents WHERE id=?', (identifier,)).fetchone()
    result = {'name': row['name']}
    if row['initial_assignment'] is not None:
        result['initial_assignment'] = row['initial_assignment']
        if row['latest_assignment'] != row['initial_assignment']:
            result['latest_assignment'] = row['latest_assignment']
        result['excerpts_truncated'] = bool(row['initial_truncated'] or row['latest_truncated'])
    if evidence and evidence['text'] not in (row['initial_assignment'], row['latest_assignment']):
        result['matching_history'] = evidence
    return result


def select_candidates(catalog, query, history='', limit=MAX_CANDIDATES):
    ranked = ranked_candidates(catalog, query, history)
    if catalog.count() <= limit:
        matches = {item['name']: item for item in ranked}
        with catalog.connect() as db:
            db.execute('BEGIN')
            return [matches.get(row['name']) or _profile(db, row['id'])
                    for row in db.execute('SELECT id,name FROM agents ORDER BY id LIMIT ?', (limit,))]
    return ranked[:limit]


def _offset(offset, count):
    if type(offset) is not int or not 0 <= offset <= count:
        raise ValueError('offset must be an integer within the available result window')


def search_names(catalog, query, offset=0):
    if not isinstance(query, str) or not normalize(query):
        raise ValueError('query must contain at least one word or number')
    candidates = ranked_candidates(catalog, query)
    _offset(offset, len(candidates))
    end = offset + SEARCH_PAGE_SIZE
    page = candidates[offset:end]
    return {'agents': [item['name'] for item in page], 'candidates': page,
            'has_more': end < len(candidates), 'next_offset': end if end < len(candidates) else None,
            'result_window': SEARCH_POOL_SIZE}


def inspect_history(catalog, agent_name, logs, offset=0):
    if not isinstance(agent_name, str) or not catalog.contains(agent_name):
        raise ValueError('agent_name must exactly match an existing agent')
    logs.sync_agent(agent_name)
    with catalog.connect() as db:
        count = db.execute('SELECT count(*) FROM entries WHERE name=?', (agent_name,)).fetchone()[0]
        _offset(offset, count)
        rows = db.execute('SELECT kind,timestamp,substr(text,1,1000) AS excerpt,length(text) AS length,position FROM entries WHERE name=? ORDER BY position DESC LIMIT 6 OFFSET ?', (agent_name, offset))
        entries = [{'type': r['kind'], 'timestamp': r['timestamp'], 'text': r['excerpt'],
                    'truncated': r['length'] > 1000, 'source': f"{agent_name}:{r['position']}"} for r in rows]
    return {'agent_name': agent_name, 'entries': entries, 'total_matches': count,
            'next_offset': offset + 6 if offset + 6 < count else None}


def ownership_profile(agent_name, logs):
    with logs.catalog.connect() as db:
        row = db.execute('SELECT id FROM agents WHERE name=?', (agent_name,)).fetchone()
        return _profile(db, row[0]) if row else {'name': agent_name}
