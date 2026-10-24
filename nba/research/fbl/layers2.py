import numpy as np
import layers as L
for n in ['t_tipd', 't_team', 'p_opp_rec', 'o_x_ef10', 'o_x_ef', 'o_t_opp_allow', 'f_sh3_sea', 'o_x_tfl', 'o_x_tf10']:
    i = L.NM.index(n); f = L.F[:, i]; q1, q2 = np.quantile(f, [1/3, 2/3]); out = []
    for S in range(2021, 2026):
        s = L.Sn == S; out.append((L.U[s & (f >= q2)].mean() - L.U[s & (f <= q1)].mean()))
    print(f'{n:14s} top-minus-bottom ROI by season: ' + ' '.join(f'{x:+.0%}' for x in out), f' seasons same sign: {max(sum(x>0 for x in out), sum(x<0 for x in out))}/5')
