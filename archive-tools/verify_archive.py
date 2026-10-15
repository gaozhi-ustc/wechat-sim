#!/usr/bin/env python3
"""LOCAL final archival verification; no project imports, production DB or network."""
from pathlib import Path
import os,json,hashlib,stat,datetime,collections,subprocess
B=Path('/tmp/wxview92');A=B/'wechat-sim';R=B/'upgrade_20261010T1529'
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for data in iter(lambda:f.read(1024*1024),b''):h.update(data)
 return h.hexdigest()
def private_write(p,data):
 with os.fdopen(os.open(p,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'wb') as f:f.write(data)
rows=[json.loads(s) for s in (A/'records/copy-manifest.jsonl').read_text().splitlines()]
ext=[json.loads(s) for s in (A/'records/external-file-manifest.jsonl').read_text().splitlines()]
assert len(set(r['archive'] for r in rows))==len(rows)
for r in rows:
 src=Path(r['source']);dst=A/r['archive']
 assert digest(src)==r['source_sha256'],('source changed',r['source'])
 assert digest(dst)==r['archive_sha256'],('archive mismatch',r['archive'])
 assert dst.stat().st_size==r['archive_bytes']
for r in ext:
 assert digest(Path(r['source']))==r['source_sha256']
 assert digest(A/r['archive'])==r['archive_sha256']
ex=json.loads((A/'records/excluded-files.json').read_text())
all_sources={str(p.relative_to(B)) for p in B.rglob('*') if A not in p.parents and p.is_file()}
indexed={r['archive'].removeprefix('snapshot/') for r in rows}|{r['relative_path'] for r in ex}
assert all_sources==indexed,('coverage mismatch', sorted(all_sources-indexed),sorted(indexed-all_sources))
# Confirm existing staged/index/worktree status was not altered by archival work.
z=subprocess.run(['git','-C',str(R),'status','--short','--branch'],capture_output=True,check=True)
assert z.stdout==(A/'records/git-status.txt').read_bytes()
z=subprocess.run(['git','-C',str(R),'ls-files','--stage'],capture_output=True,check=True)
assert z.stdout==(A/'records/git-index-files.txt').read_bytes()
for p in (A/'records/git-staged').iterdir():
 data=subprocess.run(['git','-C',str(R),'show',':'+p.name],capture_output=True,check=True).stdout
 assert hashlib.sha256(data).hexdigest()==digest(p)
scan=json.loads((A/'records/sensitive-scan.json').read_text())
assert scan['unclassified_candidates']==0 and not scan['high_confidence_patterns']
assert scan['result']=='PASS_WITH_SCOPE_LIMITS'
# Sensitive-name prohibition with documented safe path references only.
for p in A.rglob('*'):
 assert not p.is_symlink(),('symlink',str(p))
 if p.is_dir():os.chmod(p,0o700)
 elif p.is_file():os.chmod(p,0o600)
 assert stat.S_IMODE(p.stat().st_mode)==(0o700 if p.is_dir() else 0o600),str(p)
 assert p.suffix not in ('.db','.sqlite3','.pyc','.pyo'),('forbidden archive',str(p))
 assert p.name not in ('lease_token','id_rsa','id_ed25519'),('credential',str(p))
assert not list(A.rglob('__pycache__'))
assert (A/'agent.md').stat().st_size>600000 and len((A/'agent.md').read_text().splitlines())>4000
# Manifest hashes all regular archive files except itself and its referencing report.
outputs={A/'records/final-file-manifest.jsonl',A/'records/final-verification.json'}
files=sorted(p for p in A.rglob('*') if p.is_file() and p not in outputs)
manifest=[dict(path=str(p.relative_to(A)),bytes=p.stat().st_size,sha256=digest(p),mode='0600') for p in files]
blob=b''.join((json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n').encode() for r in manifest)
mp=A/'records/final-file-manifest.jsonl';private_write(mp,blob)
report=dict(result='PASS',completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),host=os.uname().nodename,archive_root=str(A),agent_md=dict(path=str(A/'agent.md'),bytes=(A/'agent.md').stat().st_size,lines=len((A/'agent.md').read_text().splitlines()),sha256=digest(A/'agent.md')),copy_files=len(rows),copy_bytes=sum(r['archive_bytes'] for r in rows),byte_identical_copy_files=sum(r['source_sha256']==r['archive_sha256'] for r in rows),redacted_copy_files=sum(r['source_sha256']!=r['archive_sha256'] for r in rows),excluded_files=len(ex),excluded_reasons=dict(collections.Counter(r['reason'] for r in ex)),known_external_plans_copied=len(ext),all_available_source_files_accounted_for=True,all_copy_source_hashes_unchanged=True,all_copy_archive_hashes_match=True,original_git_status_and_index_unchanged=True,original_staged_7_versions_export_verified=True,all_directories_mode='0700',all_files_mode='0600',no_symlinks_or_caches_or_sqlite_or_credentials=True,sensitive_scan=dict(result=scan['result'],text_files=scan['text_files_scanned'],synthetic_fixture_candidates_reviewed=scan['fixture_matches_reviewed'],unclassified_candidates=0,high_confidence_patterns=0,limitations=scan['limitations']),manifest=dict(path=str(mp),files_hashed=len(manifest),sha256=hashlib.sha256(blob).hexdigest(),excluded_from_self_hash=['records/final-file-manifest.jsonl','records/final-verification.json']),total_regular_files=len(files)+2,total_bytes=0,no_target_access_after_pause=True,project_state='PAUSED',business_complete=False,known_history_gaps=['Full original human chat/tool transcripts outside locally retained handoff and evidence','Remote-only production DB/operation logs/credentials not retrieved','Previously deleted temporary artifacts cannot be reconstructed'],terminal='All project children completed or confirmed killed; only this local archive verification shell remained and its exit0 must be collected before final response.')
# Fixed-point total includes actual report bytes itself, without circular file hashing.
for i in range(12):
 data=(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode()
 total=sum(p.stat().st_size for p in files)+len(blob)+len(data)
 if total==report['total_bytes']:break
 report['total_bytes']=total
else:raise RuntimeError('report size did not converge')
private_write(A/'records/final-verification.json',data)
assert sum(p.stat().st_size for p in A.rglob('*') if p.is_file())==report['total_bytes']
assert len([p for p in A.rglob('*') if p.is_file()])==report['total_regular_files']
print(json.dumps({k:report[k] for k in ('result','host','archive_root','total_regular_files','total_bytes','copy_files','copy_bytes','redacted_copy_files','excluded_files','agent_md','manifest')},ensure_ascii=False))
