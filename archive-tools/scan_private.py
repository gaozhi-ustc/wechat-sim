#!/usr/bin/env python3
"""Local text/credential filename archival scan. Does not OCR images/import project code."""
from pathlib import Path
import re,json,os,datetime
A=Path('/tmp/wxview92/wechat-sim')
KEYS='lease_token|session_secret|capability_token|token|secret|lease|capability|password|passwd|api_key|access_token|refresh_token|private_key|authorization|cookie|cookies|credential|credentials'
QUOTED=re.compile(r'''["'](?P<k>'''+KEYS+r''')["']\s*[:=]\s*["'](?P<v>[^"'\n]{1,4096})["']''',re.I)
ESC=re.compile(r'''\\"(?P<k>'''+KEYS+r''')\\"\s*:\s*\\"(?P<v>[^\\\n]{1,4096})\\"''',re.I)
BARE=re.compile(r'''\b(?P<k>password|passwd|api_key|access_token|refresh_token|session_secret|lease_token|capability_token|secret)\s*=\s*["'](?P<v>[^"'\n]{1,4096})["']''',re.I)
OTHER=re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----|\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b|\bBearer\s+[A-Za-z0-9._~+/-]{24,}',re.I)
TEXT={'.py','.pyi','.json','.jsonl','.log','.txt','.md','.stderr','.csv','.sh','.diff','.patch','.toml','.ini','.cfg','.yaml','.yml','.html','.xml','.rst','.c','.h','.f','.f90','.al','.cmake',''}
rows=[]; high=[]; count=0; pathrefs=0; placeholders=0; inline_fake=0
for p in sorted(A.rglob('*')):
 if not p.is_file() or p.suffix.lower() not in TEXT or p.name in ('sensitive-scan.json','final-file-manifest.jsonl','final-verification.json'):continue
 if p.suffix=='' and p.name not in ('METADATA','WHEEL','RECORD','LICENSE','PKG-INFO','config','lease_token'):continue
 data=p.read_bytes()
 try:s=data.decode('utf-8')
 except UnicodeError:continue
 count+=1
 for rx in (QUOTED,ESC,BARE):
  for m in rx.finditer(s):
   v=m['v']; key=m['k'].lower();line=s.count('\n',0,m.start())+1
   if v.startswith('/'):pathrefs+=1;continue
   if v=='[REDACTED_PRIVATE_AUTHORITY_VALUE]' or v.startswith('<'):placeholders+=1;continue
   # All other strings must be classified by archive-only read-only review.
   rows.append(dict(path=str(p.relative_to(A)),line=line,key=key,length=len(v),fixture_source=('test' in p.name or 'fixture' in str(p)),synthetic_hint=(v in ('ignored','token','fake','test','s','a','wrong','redacted','secret','OLD','LEASE','RAW','MOCK','not-printed','lease-private') or v.startswith(('SECRET','FAKE','fake','bad','wrong','L','s3cr','known','private-'))),hex_digest=bool(re.fullmatch('[a-fA-F0-9]{64}',v))))
 for m in OTHER.finditer(s):high.append(dict(path=str(p.relative_to(A)),line=s.count('\n',0,m.start())+1,pattern='private-key/cloud-token/Bearer-shaped literal; no value exported'))
out=dict(captured_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope='archive local UTF-8 text; no SSH/UI/OCR',text_files_scanned=count,path_reference_matches=pathrefs,placeholder_matches=placeholders,candidates=rows,high_confidence_patterns=high,limitations=['Does not OCR private screenshots or decode binaries/models; private archive is not for public/Git release.','Keyword matches are not proof of real secret; synthetic fixtures and file-hash keys require context classification.','Excluded original credential/lease/private key files never read; no value exported in this report.'])
p=A/'records/sensitive-scan.json'
with os.fdopen(os.open(p,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w') as f:json.dump(out,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps(dict(scanned=count,candidates=len(rows),high=len(high),pathrefs=pathrefs,placeholders=placeholders)))
