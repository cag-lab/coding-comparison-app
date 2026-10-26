# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent reference implementations of Cohen's kappa, Krippendorff's alpha
(general coincidence-matrix form) and Shrout & Fleiss ICC, used to cross-check the
JavaScript core on the example files. Requires numpy; scikit-learn is optional.

Usage: python3 tests/reference_check.py
"""
import json, re, itertools
from pathlib import Path
import numpy as np
try:
    from sklearn.metrics import cohen_kappa_score
except Exception: cohen_kappa_score=None
def kripp(data, metric):  # general: rows=coders, cols=units, np.nan missing
    vals=sorted({v for v in data.flatten() if not np.isnan(v)}); idx={v:i for i,v in enumerate(vals)}
    o=np.zeros((len(vals),len(vals)))
    for u in data.T:
        p=[v for v in u if not np.isnan(v)]; m=len(p)
        if m<2: continue
        for i,j in itertools.permutations(range(m),2): o[idx[p[i]],idx[p[j]]]+=1/(m-1)
    nc=o.sum(1); n=nc.sum()
    d=lambda a,b: (a!=b)*1.0 if metric=='nominal' else (a-b)**2
    D=np.array([[d(a,b) for b in vals] for a in vals])
    Do=(o*D).sum()/n; De=(np.outer(nc,nc)*D).sum()/(n*(n-1)); return 1-Do/De
def icc(Y):  # n x k, Shrout & Fleiss
    n,k=Y.shape; gm=Y.mean()
    BMS=k*((Y.mean(1)-gm)**2).sum()/(n-1); JMS=n*((Y.mean(0)-gm)**2).sum()/(k-1)
    EMS=(((Y-gm)**2).sum()-BMS*(n-1)-JMS*(k-1))/((n-1)*(k-1))
    return (BMS-EMS)/(BMS+(k-1)*EMS+k*(JMS-EMS)/n), (BMS-EMS)/(BMS+(k-1)*EMS)
EX = Path(__file__).resolve().parent.parent / 'examples'
a=json.load(open(EX/'synthetic-icu-progress-note__cag__coding.json'))
b=json.load(open(EX/'synthetic-icu-progress-note__cag2__coding.json'))
text=a['note']['text']
units=[(m.start(), m.end()) for m in re.finditer(r'\S+', text)]  # token units
codes=sorted({x['code'] for x in a['annotations']+b['annotations']})
def cov(anns, code):
    out=[]
    for s,e in units:
        nw=[i for i in range(s,e) if not text[i].isspace()]
        out.append(sum(1 for i in nw if any(x['code']==code and x['start']<=i<x['end'] for x in anns))/len(nw))
    return np.array(out)
for code in codes:
    ca,cb=cov(a['annotations'],code),cov(b['annotations'],code); pa,pb=(ca>0)*1.,(cb>0)*1.
    k=cohen_kappa_score(pa,pb) if cohen_kappa_score else float('nan')
    i2,i3=icc(np.vstack([ca,cb]).T)
    print(f"{code:28s} kappa {k:.6f} alpha {kripp(np.vstack([pa,pb]),'nominal'):.6f} ICC2 {i2:.6f} ICC3 {i3:.6f}")
cnt=lambda d:[sum(x['code']==c for x in d['annotations']) for c in codes]
ca=np.array(cnt(a),float);cb=np.array(cnt(b),float)
print('counts alpha %.6f'%kripp(np.vstack([ca,cb]),'interval'), 'ICC2/3 %.6f %.6f'%icc(np.vstack([ca,cb]).T))

# Expected values asserted by tests/core.test.mjs for the JavaScript core.
EXPECTED = {'kappa': 0.381337, 'alpha': 0.380018, 'icc2': 0.381654, 'icc3': 0.383483}
ca, cb = cov(a['annotations'], 'physiological_failure'), cov(b['annotations'], 'physiological_failure')
pa, pb = (ca > 0) * 1., (cb > 0) * 1.
i2, i3 = icc(np.vstack([ca, cb]).T)
got = {'alpha': kripp(np.vstack([pa, pb]), 'nominal'), 'icc2': i2, 'icc3': i3}
if cohen_kappa_score: got['kappa'] = cohen_kappa_score(pa, pb)
bad = {k: v for k, v in got.items() if abs(v - EXPECTED[k]) > 1e-5}
if bad:
    raise SystemExit(f'MISMATCH vs JS core expectations: {bad}')
print('PASS: reference values match the JavaScript core expectations')
