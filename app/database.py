import json
import sqlite3
from contextlib import contextmanager
from uuid import uuid4

class Database:
    def __init__(self, path):
        self.path = path
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS versions (
                  id TEXT PRIMARY KEY, company_id TEXT NOT NULL, number INTEGER NOT NULL,
                  document TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN
                  ('STAGING','ACTIVE','SUPERSEDED','FAILED')),
                  created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, error TEXT,
                  UNIQUE(company_id,number), UNIQUE(company_id,id));
                CREATE UNIQUE INDEX IF NOT EXISTS one_active ON versions(company_id)
                  WHERE status='ACTIVE';
                CREATE TABLE IF NOT EXISTS active (company_id TEXT PRIMARY KEY,
                  version_id TEXT NOT NULL, FOREIGN KEY(company_id,version_id)
                  REFERENCES versions(company_id,id));
                CREATE TABLE IF NOT EXISTS chunks (id TEXT PRIMARY KEY, company_id TEXT NOT NULL,
                  version_id TEXT NOT NULL, payload TEXT NOT NULL,
                  FOREIGN KEY(company_id,version_id) REFERENCES versions(company_id,id));
                CREATE INDEX IF NOT EXISTS chunk_scope ON chunks(company_id,version_id);
                CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, company_id TEXT NOT NULL,
                  actor TEXT NOT NULL, event TEXT NOT NULL, request_id TEXT NOT NULL,
                  detail TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS answers (request_id TEXT PRIMARY KEY, company_id TEXT NOT NULL,
                  actor TEXT NOT NULL, version_id TEXT, status TEXT NOT NULL, calls INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS feedback (request_id TEXT PRIMARY KEY REFERENCES answers(request_id),
                  helpful INTEGER NOT NULL, reason TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  event_type TEXT, company_id TEXT, user_id TEXT, details TEXT, created_at INTEGER);
            ''')
    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()
    def active(self, company):
        with self.connect() as db:
            row = db.execute('SELECT version_id FROM active WHERE company_id=?', (company,)).fetchone()
            return row[0] if row else None
    def stage(self, company, document):
        version = uuid4().hex
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            number = db.execute('SELECT COALESCE(MAX(number),0)+1 FROM versions WHERE company_id=?', (company,)).fetchone()[0]
            db.execute('INSERT INTO versions(id,company_id,number,document,status) VALUES(?,?,?,?,?)',
                       (version, company, number, document, 'STAGING'))
        return version
    def activate(self, company, version, chunks, actor, request_id):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status FROM versions WHERE id=? AND company_id=?', (version, company)).fetchone()
            if not row or row[0] != 'STAGING' or not chunks:
                raise ValueError('Invalid activation state')
            for chunk in chunks:
                if chunk.company_id != company or chunk.policy_version != version:
                    raise ValueError('Chunk scope mismatch')
                db.execute('INSERT INTO chunks VALUES(?,?,?,?)', (chunk.chunk_id, company, version, chunk.model_dump_json()))
            db.execute("UPDATE versions SET status='SUPERSEDED' WHERE company_id=? AND status='ACTIVE'", (company,))
            db.execute("UPDATE versions SET status='ACTIVE' WHERE id=? AND company_id=?", (version, company))
            db.execute('INSERT INTO active VALUES(?,?) ON CONFLICT(company_id) DO UPDATE SET version_id=excluded.version_id', (company, version))
            self._audit(db, company, actor, 'policy_activated', request_id, {'version': version, 'chunks': len(chunks)})
            result = dict(db.execute('SELECT * FROM versions WHERE id=? AND company_id=?', (version, company)).fetchone())
        return result
    def fail(self, company, version, actor, request_id, code):
        with self.connect() as db:
            db.execute("UPDATE versions SET status='FAILED',error=? WHERE id=? AND company_id=? AND status='STAGING'", (code, version, company))
            self._audit(db, company, actor, 'ingestion_failed', request_id, {'version': version, 'code': code})
    @staticmethod
    def _audit(db, company, actor, event, request_id, detail):
        db.execute('INSERT INTO audit(company_id,actor,event,request_id,detail) VALUES(?,?,?,?,?)',
                   (company, actor, event, request_id, json.dumps(detail)))
    def audit(self, company, actor, event, request_id, detail):
        with self.connect() as db:
            self._audit(db, company, actor, event, request_id, detail)
    def versions(self, company):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM versions WHERE company_id=? ORDER BY number DESC', (company,))]
    def staging(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM versions WHERE status IN ('STAGING','FAILED')")]
    def active_versions(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM versions WHERE status='ACTIVE'")]
    def chunks(self, company, version):
        from app.schemas import Chunk
        with self.connect() as db:
            return [Chunk.model_validate_json(r[0]) for r in db.execute(
                'SELECT payload FROM chunks WHERE company_id=? AND version_id=? ORDER BY id', (company, version))]
    def record_answer(self, p, response):
        with self.connect() as db:
            db.execute('INSERT INTO answers VALUES(?,?,?,?,?,?)',
                       (response.request_id, p.company_id, p.user_id, response.policy_version, response.status, response.llm_calls))
            self._audit(db, p.company_id, p.user_id, 'chat', response.request_id,
                        {'status': response.status, 'version': response.policy_version, 'calls': response.llm_calls})
    def feedback(self, p, body):
        with self.connect() as db:
            row = db.execute('SELECT 1 FROM answers WHERE request_id=? AND company_id=? AND actor=?',
                             (body.request_id, p.company_id, p.user_id)).fetchone()
            if not row:
                return False
            db.execute('INSERT INTO feedback VALUES(?,?,?) ON CONFLICT(request_id) DO UPDATE SET helpful=excluded.helpful,reason=excluded.reason',
                       (body.request_id, int(body.helpful), body.reason))
            self._audit(db, p.company_id, p.user_id, 'feedback', body.request_id, {'helpful': body.helpful})
        return True
    def events(self, company, limit, offset):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM audit WHERE company_id=? ORDER BY id DESC LIMIT ? OFFSET ?', (company, limit, offset))]
