from rules import run, fmt
print('== D. EV threshold x daily cap (all prices, blend prob, 1/game) ==')
for t in (0.0,0.1,0.2,0.3,0.4,0.5,0.6,0.8,1.0):
    for cap in (1,2,3,5,None):
        print(fmt(f'EV>={t:.1f} cap={cap} fallback', run(ev_min=t,per_day=cap,fallback=True)))
print()
print('== E. Which probability layer (EV>=.3, cap3, fallback) ==')
for prob in ('pb','p','pm'):
    print(fmt(f'prob={prob}', run(prob=prob)))
print(fmt('prob=pm EV>=0 nocap (market alone)', run(prob='pm',ev_min=0,per_day=None,fallback=False)))
print()
print('== F. Jumpers vs non-jumpers (EV>=.3 cap3) ==')
print(fmt('jumpers only', run(jumper=True))); print(fmt('non-jumpers only', run(jumper=False)))
print(fmt('jumpers only EV>=0 nocap', run(jumper=True,ev_min=0,per_day=None,fallback=False)))
print()
print('== G. Ranking within the day (EV>=.3 cap3) ==')
for rk in ('ev','p','ratio'):
    print(fmt(f'rank={rk}', run(rank=rk)))
print()
print('== H. Line shopping: best book price instead of FanDuel ==')
print(fmt('best price, EV>=.3 cap3', run(price='dbest')))
print(fmt('best price, EV>=.3 nocap', run(price='dbest',per_day=None,fallback=False)))
print()
print('== I. Probability floors (EV>=.3, cap3): need at least p ==')
for mp in (0.06,0.08,0.10,0.12):
    print(fmt(f'p>={mp}', run(min_p=mp)))
