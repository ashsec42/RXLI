#!/usr/bin/env python3
candidates = set()
for f in found:
if not f:
continue
if f.startswith("/"):
candidates.add("https://g5nl6xoalpq6-hls-live.5centscdn.com" + f)
else:
candidates.add(f)
return sorted(candidates)




def probe_url(url):
try:
# try HEAD first
r = requests.head(url, headers=HEADERS, timeout=6, allow_redirects=True)
if r.status_code >= 400 or 'mpegurl' not in r.headers.get('Content-Type', '').lower():
r = requests.get(url, headers=HEADERS, timeout=8)
return {'url': url, 'status': r.status_code, 'body': r.text}
except Exception as e:
return {'url': url, 'status': None, 'error': str(e)}




def is_master(body):
if not body:
return False
return '#EXT-X-STREAM-INF' in body




def write_master(body):
tmp = OUT_PATH + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
f.write(body)
# atomic replace
os.replace(tmp, OUT_PATH)
print(f"[+] wrote master to {OUT_PATH}")




if __name__ == '__main__':
candidates = find_candidates_simple()
print('[*] candidates=', candidates)
best = None
for c in candidates:
print('[*] probing', c)
res = probe_url(c)
if res.get('status') and res.get('status') < 400 and res.get('body'):
if is_master(res['body']):
print('[+] found master at', c)
write_master(res['body'])
best = c
break
if not best:
print('[-] no master found in simple mode')
# exit success so actions continues; you can change return code if desired
else:
# print small confirmation
print('[+] done')
