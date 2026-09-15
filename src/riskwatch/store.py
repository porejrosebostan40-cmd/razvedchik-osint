import hashlib, json, sqlite3, time
from .config import SETTINGS
class Store:
    def __init__(self,path=None):
        self.db=sqlite3.connect(path or SETTINGS.db_path); self.db.row_factory=sqlite3.Row
        self.db.executescript('CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,ts REAL,source TEXT,url TEXT,title TEXT,snippet TEXT,query TEXT,region TEXT,kind TEXT); CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY,ts REAL,risk INTEGER,probability INTEGER,confidence INTEGER,decision TEXT,reason TEXT,raw TEXT);'); self.db.commit()
    def add_events(self,events):
        n=0
        for e in events:
            eid=hashlib.sha256((e['url']+'|'+e['title']).encode()).hexdigest()
            try:
                self.db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?)',(eid,time.time(),e.get('source',''),e.get('url',''),e.get('title',''),e.get('snippet',''),e.get('query',''),e.get('region',''),e.get('kind',''))); n+=1
            except sqlite3.IntegrityError: pass
        self.db.commit(); return n
    def recent(self,limit=80): return [dict(x) for x in self.db.execute('SELECT * FROM events ORDER BY ts DESC LIMIT ?',(limit,)).fetchall()]
    def save_decision(self,d):
        self.db.execute('INSERT INTO decisions(ts,risk,probability,confidence,decision,reason,raw) VALUES(?,?,?,?,?,?,?)',(time.time(),d.get('risk',0),d.get('probability',0),d.get('confidence',0),d.get('decision',''),d.get('reason',''),json.dumps(d,ensure_ascii=False))); self.db.commit()
