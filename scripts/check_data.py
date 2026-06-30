import json
with open('data/market_data.json', encoding='utf-8') as f:
    d = json.load(f)

print("=== VIX ===")
for k, v in d['vix'].items():
    print(f"  {k}: {v.get('current', 'N/A')}")

print("\n=== CNN F&G ===")
cnn = d['cnn_fear_greed']
print(f"  score={cnn.get('current')} rating={cnn.get('rating')}")

print("\n=== Institutional (億元) ===")
inst = d['institutional']
for k in ['foreign','investment_trust','dealer','total_net']:
    v = inst.get(k)
    if v is not None:
        print(f"  {k}: {round(v/100000000, 2):.2f} 億")
    else:
        print(f"  {k}: N/A")

print("\n=== Signal ===")
sig = d['signal']
print(f"  score: {sig['score']:+.1f}  outlook: {sig['outlook']} ({sig['outlook_en']})")
for det in sig.get('details', []):
    print(f"  [{det['indicator']}] value={det['value']} signal={det['signal']:+d} weight={det['weight']}")

print("\n=== History days ===")
for k, v in d.get('vix_history', {}).items():
    print(f"  {k}: {len(v.get('dates',[]))} days")
print(f"  institutional: {len(inst.get('history',[]))} days")
