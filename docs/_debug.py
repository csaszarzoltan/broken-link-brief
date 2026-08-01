import sqlite3
db = sqlite3.connect(':memory:')
db.row_factory = sqlite3.Row
db.execute('''CREATE TABLE scan_history (
    id TEXT PRIMARY KEY, project_id TEXT, scan_timestamp TEXT,
    total_urls INT, total_links INT, broken_count INT,
    new_broken_count INT DEFAULT 0, status TEXT DEFAULT 'completed',
    raw_results_json TEXT, last_known_good_hash TEXT, regression_flags TEXT
)''')
db.execute('INSERT INTO scan_history VALUES (?,?,?,?,?,?,?,?,?,?,?)',
    ('abc', 'proj1', '2026-08-01', 1, 2, 0, 0, 'completed', None, None, None))
db.commit()
row = db.execute('SELECT * FROM scan_history WHERE project_id=?', ('proj1',)).fetchone()
print(type(row))
print(list(row.keys()))
print({k: row[k] for k in row.keys()})
