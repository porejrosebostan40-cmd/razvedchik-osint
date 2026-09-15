import json, requests
from .config import SETTINGS
SYSTEM='''Ты аналитическое ядро системы раннего предупреждения. Анализируй только переданные факты. Не превращай слух в факт. Отделяй официальное подтверждение, независимое подтверждение, слух и отсутствие данных. Не утверждай, что событие произойдет. Оцени сценарий, вероятность, уверенность и риск для человека, находящегося в учреждении ФСИН. Учитывай временную последовательность, независимость источников, повторяемость признаков и альтернативные объяснения. Верни только JSON с полями probability, confidence, risk, decision, reason, signals, missing_indicators.'''
def analyze(events):
    if not SETTINGS.openai_api_key: return {"probability":0,"confidence":0,"risk":0,"decision":"NO_AI_KEY","reason":"OPENAI_API_KEY is not configured","signals":[],"missing_indicators":[]}
    payload={"model":SETTINGS.openai_model,"input":[{"role":"system","content":SYSTEM},{"role":"user","content":json.dumps({"scenario":"мобилизационные или связанные с ФСИН действия после 20 сентября 2026 года","events":events[-100:]},ensure_ascii=False)}],"text":{"format":{"type":"json_object"}},"store":False}
    r=requests.post("https://api.openai.com/v1/responses",headers={"Authorization":f"Bearer {SETTINGS.openai_api_key}","Content-Type":"application/json"},json=payload,timeout=60); r.raise_for_status(); data=r.json()
    text=data.get("output_text","")
    if not text:
        for item in data.get("output",[]):
            for c in item.get("content",[]):
                if c.get("type")=="output_text": text=c.get("text","")
    return json.loads(text)
