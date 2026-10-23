from rules import run, fmt
print('== A. Every bet one-per-game with EV>=t, no daily cap, by FanDuel price band ==')
bands=[(None,299),(300,499),(500,699),(700,999),(1000,1499),(1500,2499),(2500,None)]
for t in (0.0,0.1,0.3):
    for lo,hi in bands:
        print(fmt(f'EV>={t:.1f} price {lo or "":>5}..{hi or "":<5} nocap', run(ev_min=t,lo=lo,hi=hi,per_day=None,fallback=False)))
    print()
print('== B. No value filter at all: everyone in band (shows how the book prices each band) ==')
for lo,hi in bands:
    print(fmt(f'ALL starters price {lo or "":>5}..{hi or "":<5}', run(ev_min=-9,lo=lo,hi=hi,per_day=None,fallback=False)))
print()
print('== C. The "middle": +500..+999 with value, various caps ==')
for t in (0.0,0.1,0.2,0.3):
    for cap in (1,3,None):
        print(fmt(f'mid 500..999 EV>={t:.1f} cap={cap}', run(ev_min=t,lo=500,hi=999,per_day=cap,fallback=False)))
