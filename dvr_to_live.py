#!/usr/bin/env python3
return ref
return urllib.parse.urljoin(base, ref)




def build_live(playlist_text, base_url, n=N_SEGMENTS):
lines = [l.strip() for l in playlist_text.splitlines() if l.strip() != '']
segs = []
i = 0
while i < len(lines):
if lines[i].startswith('#EXTINF'):
if i+1 < len(lines):
segs.append((lines[i], lines[i+1]))
i += 2
continue
i += 1
if not segs:
raise RuntimeError('no segments found')
tail = segs[-n:] if len(segs) >= n else segs
td = 6
for l in lines:
if l.startswith('#EXT-X-TARGETDURATION'):
try:
td = int(l.split(':',1)[1])
except:
pass
break
media_seq = None
for l in lines:
if l.startswith('#EXT-X-MEDIA-SEQUENCE'):
try:
media_seq = int(l.split(':',1)[1])
except:
media_seq = None
break
if media_seq is None:
media_seq = 0
first_seq = media_seq + (len(segs) - len(tail))
out = ['#EXTM3U', '#EXT-X-VERSION:3', f'#EXT-X-TARGETDURATION:{td}', f'#EXT-X-MEDIA-SEQUENCE:{first_seq}']
for extinf, uri in tail:
out.append(extinf)
out.append(make_absolute(base_url, uri))
return '
'.join(out) + '
'




def main():
playlist_text = fetch_text(PLAYLIST_URL)
# If the fetched playlist is a master (contains EXT-X-STREAM-INF), save it as .m3u
if '#EXT-X-STREAM-INF' in playlist_tex
