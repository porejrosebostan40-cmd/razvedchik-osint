import hashlib, json, os, time
class Store:
    def __init__(self,path=None):
        self.path=path or os.getenv("RISKWATCH_STATE","riskwatch_state.json")
        try: self.data=json.load(open(self.path,encoding="utf-8"))
        except (FileNotFoundError,json.JSONDecodeError): self.data={"events":{},"decisions":[]}
    def add_events(self,events):
        n=0
        for e in events:
            eid=hashlib.sha256((e.get('url','')+'|'+e.get('title','')).encode()).hexdigest()
            if eid not in self.data["events"]: self.data["events"][eid]={**e,"ts":time.time()}; n+=1
        self._save(); return n
    def recent(self,limit=120): return sorted(self.data["events"].values(),key=lambda x:x.get("ts",0))[-limit:]
    def save_decision(self,d):
        self.data["decisions"].append({"ts":time.time(),**d}); self.data["decisions"]=self.data["decisions"][-500:]; self._save()
    def _save(self):
        tmp=self.path+'.tmp'; json.dump(self.data,open(tmp,'w',encoding='utf-8'),ensure_ascii=False,indent=2); os.replace(tmp,self.path)
