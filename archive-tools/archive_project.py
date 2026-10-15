#!/usr/bin/env python3
"""One-time LOCAL archival copy. Never imports project code or touches target/DB."""
import os, re, json, hashlib, stat, subprocess, datetime
from pathlib import Path
B=Path('/tmp/wxview92'); A=B/'wechat-sim'; D=A/'snapshot'
SENSITIVE={'lease','lease_token','token','secret','credential','credentials','capability','capability_token','password','passwd','api_key','access_token','private_key','authorization','cookie','cookies','session_secret'}
TEXT={'.py','.pyi','.json','.jsonl','.log','.txt','.md','.stderr','.csv','.sh','.diff','.patch','.toml','.ini','.cfg','.yaml','.yml','.html','.xml','.rst','.c','.h','.f','.f90','.al','.cmake'}
RE=re.compile(r'''(["'](?:lease|lease_token|session_secret|capability_token|token|secret|capability|password|passwd|api_key|access_token|private_key|authorization|cookie)["']\s*[:=]\s*)(["'])([^"'\n]+)\2''',re.I)
ESC=re.compile(r'''(\\["'](?:lease|lease_token|session_secret|capability_token|token|secret|capability|password|passwd|api_key|access_token|private_key|authorization|cookie)\\["']\s*:\s*)\\["']([^\\\n]+)\\["']''',re.I)
PLACE='[REDACTED_PRIVATE_AUTHORITY_VALUE]'
def sha(data):return hashlib.sha256(data).hexdigest()
def safe_value(v):
 return v is None or v=='' or v==PLACE or (isinstance(v,str) and (v.startswith('/') or v.startswith('<') or v in ('ignored','token','fake','test','s','a','wrong','redacted') or v.endswith(('.secret','.json','.py'))))
def scrub(v):
 if isinstance(v,dict):
  return {k: (PLACE if str(k).lower() in SENSITIVE and not safe_value(x) else scrub(x)) for k,x in v.items()}
 if isinstance(v,list):return [scrub(x) for x in v]
 if isinstance(v,str):
  try:
   nested=json.loads(v)
   if isinstance(nested,(dict,list)):
    clean=scrub(nested)
    if clean!=nested:return json.dumps(clean,ensure_ascii=False,sort_keys=True)
  except (ValueError,RecursionError):pass
  return scrub_literals(v)
 return v
def scrub_literals(s):
 def sub(m):return m.group(0) if safe_value(m.group(3)) else m.group(1)+m.group(2)+PLACE+m.group(2)
 s=RE.sub(sub,s)
 s=ESC.sub(lambda m:m.group(0) if safe_value(m.group(2)) else m.group(1)+'\\"'+PLACE+'\\"',s)
 return s
def excluded(p):
 parts=p.relative_to(B).parts
 if '.git' in parts:return 'Git metadata: original repository/index left untouched; status and staged source export recorded separately'
 if '__pycache__' in parts or p.suffix in ('.pyc','.pyo'):return 'regenerable Python cache, not source/evidence'
 if p.suffix in ('.sqlite3','.db') or p.name.endswith(('-wal','-shm')):return 'local historical DB/backup excluded: no second ledger; original private path retained only'
 if re.search(r'(^|[._-])(secret|credential|credentials|lease_token|id_rsa|id_ed25519|private_key)([._-]|$)',p.name,re.I):return 'private credential/secret/lease/key file: NEVER read or copied'
 if p.is_symlink():return 'symlink not dereferenced'
 return None
def write(p,data):
 p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 with os.fdopen(os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as f:f.write(data)
for d in (D,A/'records'):d.mkdir(mode=0o700,exist_ok=True)
files=sorted(p for p in B.rglob('*') if A not in p.parents and p.is_file())
manifest=[]; omitted=[]; changed=[]
for p in files:
 reason=excluded(p)
 rel=str(p.relative_to(B))
 if reason:
  omitted.append(dict(source=str(p),relative_path=rel,reason=reason,size=p.stat().st_size));continue
 data=p.read_bytes();srcsha=sha(data);out=data
 if b'-----BEGIN ' in data and b'PRIVATE KEY-----' in data:
  omitted.append(dict(source=str(p),relative_path=rel,reason='private key material detected; file excluded',size=len(data)));continue
 if p.suffix in TEXT or p.name in ('config','METADATA','WHEEL','RECORD','LICENSE','LICENSE.txt','PKG-INFO'):
  try:s=data.decode('utf8')
  except UnicodeError:s=None
  if s is not None:
   if p.suffix=='.json':
    try:
     v=json.loads(s);clean=scrub(v)
     if v!=clean:out=(json.dumps(clean,ensure_ascii=False,indent=2)+'\n').encode()
    except ValueError:out=scrub_literals(s).encode()
   elif p.suffix=='.jsonl':
    lines=[]
    for line in s.splitlines(keepends=True):
     try:
      v=json.loads(line);clean=scrub(v);lines.append(line if clean==v else json.dumps(clean,ensure_ascii=False)+'\n')
     except ValueError:lines.append(scrub_literals(line))
    out=''.join(lines).encode()
   elif p.suffix not in ('.py','.pyi','.c','.h','.f','.f90'):
    out=scrub_literals(s).encode()
   # executable source is preserved exactly; private literals separately rejected
   if p.suffix in ('.py','.pyi'):
    matches=[m for m in RE.finditer(s) if not safe_value(m.group(3))]
    if matches:
     # These source occurrences are reviewed dummy fixture values, not private authority.
     if any(len(m.group(3))>=32 and '/' not in m.group(3) for m in matches):
      omitted.append(dict(source=str(p),relative_path=rel,reason='source has unclassified long authority literal; excluded fail-closed',size=len(data),source_sha256=srcsha));continue
 dest=D/rel;write(dest,out)
 if sha(p.read_bytes())!=srcsha:raise RuntimeError('source changed during archive: '+rel)
 manifest.append(dict(source=str(p),archive='snapshot/'+rel,source_sha256=srcsha,archive_sha256=sha(out),source_bytes=len(data),archive_bytes=len(out),mode='0600',transformation='sensitive-authority-redacted; not original evidence hash' if out!=data else 'byte-identical'))
 if out!=data:changed.append(rel)
write(A/'records/copy-manifest.jsonl',b''.join((json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n').encode() for r in manifest))
write(A/'records/excluded-files.json',json.dumps(omitted,ensure_ascii=False,indent=2).encode()+b'\n')
write(A/'records/archive-copy-summary.json',json.dumps(dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),host=os.uname().nodename,source_root=str(B),archive_root=str(A),copied_files=len(manifest),copied_bytes=sum(r['archive_bytes'] for r in manifest),redacted_files=changed,excluded_files=len(omitted),original_source_files_unchanged=True,no_target_operation=True,no_project_import=True),ensure_ascii=False,indent=2).encode()+b'\n')
print(json.dumps(dict(copied=len(manifest),bytes=sum(r['archive_bytes'] for r in manifest),redacted=len(changed),excluded=len(omitted))))
