import hashlib, json, os, time

MAX_EVENTS = 10000
MAX_DECISIONS = 500

class Store:
    def __init__(self,path=None):
        self.path=path or os.getenv("RISKWATCH_STATE","riskwatch_state.json")
        try:
            with open(self.path,encoding="utf-8") as f: self.data=json.load(f)
        except (FileNotFoundError,json.JSONDecodeError):
            self.data={"events":{},"decisions":[]}
        self.data.setdefault("events",{})
        self.data.setdefault("decisions",[])

    def add_events(self,events):
        n=0
        for e in events:
            eid=hashlib.sha256((e.get('url','')+'|'+e.get('title','')).encode()).hexdigest()
            if eid not in self.data["events"]:
                self.data["events"][eid]={**e,"ts":time.time()}; n+=1
        if len(self.data["events"]) > MAX_EVENTS:
            keep=sorted(self.data["events"].items(),key=lambda kv:kv[1].get("ts",0))[-MAX_EVENTS:]
            self.data["events"]=dict(keep)
        self._save(); return n

    def recent(self,limit=120):
        return sorted(self.data["events"].values(),key=lambda x:x.get("ts",0))[-limit:]

    def save_decision(self,d):
        self.data["decisions"].append({"ts":time.time(),**d})
        self.data["decisions"]=self.data["decisions"][-MAX_DECISIONS:]
        self._save()

    def _save(self):
        tmp=self.path+'.tmp'
        with open(tmp,'w',encoding='utf-8') as f:
            json.dump(self.data,f,ensure_ascii=False,indent=2)
        os.replace(tmp,self.path)
