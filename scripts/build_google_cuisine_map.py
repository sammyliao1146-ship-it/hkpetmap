"""Manual local matching; does not call external APIs."""
import json
from collections import Counter
from datetime import datetime,timezone
from backend.app.models.pet import Snapshot
from backend.app.data.google_cuisines import ROOT,MANIFEST,select_candidate,select_cuisine_candidate

def main():
    snapshot=Snapshot.model_validate_json((ROOT/'data/pet-snapshot.json').read_text())
    base=ROOT/'data/google-places';index=json.loads((base/'index.json').read_text());rows={};unmatched=[]
    for p in snapshot.places:
        if p.category!='restaurants': continue
        ids=index['restaurants'].get(p.id,{}).get('candidate_place_ids',[])
        records=[]
        for pid in ids:
            path=base/'places'/f'{pid}.json'
            if path.exists(): records.append(json.loads(path.read_text()))
        result=select_candidate(p,records) or select_cuisine_candidate(p,records)
        if result: rows[p.id]={**result,'address':p.address}
        else: unmatched.append(p.id)
    payload={'created_at':datetime.now(timezone.utc).isoformat(),'automatic_updates':False,'restaurants':rows,'unmatched_restaurant_ids':unmatched,'matching':'prefer reviewed/name-distance match; include remaining cuisine candidates as needs_review'}
    tmp=MANIFEST.with_suffix('.tmp');tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2));tmp.replace(MANIFEST)
    print(json.dumps({'matched':len(rows),'unmatched':len(unmatched),'cuisines':dict(Counter(v['cuisines'][0] for v in rows.values()))},ensure_ascii=False))
if __name__=='__main__':main()
