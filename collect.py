#!/usr/bin/env python3
"""유튜브 채널별 인기 제목 수집기 (GitHub Action에서 주1회 실행).
채널 업로드 목록을 훑어(search order=viewCount는 채널 역대 top을 안 줌) 실제 조회수로
minViews 이상만 titles.json에 채운다. 키는 env YT_API_KEY, 채널은 channels.json."""
import os, json, time, html, urllib.parse, urllib.request, urllib.error

KEY = os.environ["YT_API_KEY"]
CFG = json.load(open("channels.json", encoding="utf-8"))
MIN_VIEWS = CFG.get("minViews", 500000)
RECENT_PAGES = CFG.get("recentPages", 12)
PER_CHANNEL = CFG.get("perChannel", 40)

def api(endpoint, **params):
    params["key"] = KEY
    url = "https://www.googleapis.com/youtube/v3/" + endpoint + "?" + urllib.parse.urlencode(params)
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            try: return json.load(e)
            except Exception: return {}
        except Exception:
            time.sleep(1)
    return {}

def channel_title(cid):
    d = api("channels", part="snippet", id=cid)
    it = d.get("items", [])
    return it[0]["snippet"]["title"] if it else cid

def resolve(c):
    if c.get("id"):
        return c["id"], channel_title(c["id"])
    d = api("search", part="snippet", q=c["name"], type="channel", maxResults="1")
    it = d.get("items", [])
    return (it[0]["id"]["channelId"], it[0]["snippet"]["title"]) if it else (None, None)

def uploads_playlist(cid):
    d = api("channels", part="contentDetails", id=cid)
    it = d.get("items", [])
    return it[0]["contentDetails"]["relatedPlaylists"]["uploads"] if it else None

def playlist_ids(plid):
    ids, token = [], None
    for _ in range(RECENT_PAGES):
        p = {"part": "contentDetails", "playlistId": plid, "maxResults": "50"}
        if token: p["pageToken"] = token
        d = api("playlistItems", **p)
        for it in d.get("items", []):
            vid = it.get("contentDetails", {}).get("videoId")
            if vid: ids.append(vid)
        token = d.get("nextPageToken")
        if not token: break
    return ids

def search_top_ids(cid):
    d = api("search", part="snippet", channelId=cid, order="viewCount", type="video", maxResults="50")
    return [it["id"]["videoId"] for it in d.get("items", []) if it.get("id", {}).get("videoId")]

def stats(ids):
    out = []
    for i in range(0, len(ids), 50):
        d = api("videos", part="snippet,statistics", id=",".join(ids[i:i+50]))
        for it in d.get("items", []):
            sn, st = it.get("snippet", {}), it.get("statistics", {})
            out.append({
                "videoId": it["id"],
                "text": html.unescape(sn.get("title", "").strip()),
                "channel": html.unescape(sn.get("channelTitle", "").strip()),
                "views": int(st.get("viewCount", 0)),
            })
    return out

def main():
    all_rows, seen = [], set()
    for c in CFG["channels"]:
        cid, title = resolve(c)
        if not cid:
            print(f"skip {c['name']}: 채널 못 찾음"); continue
        pl = uploads_playlist(cid)
        ids = set(playlist_ids(pl) if pl else [])
        ids |= set(search_top_ids(cid))
        rows = [r for r in stats(list(ids)) if r["views"] >= MIN_VIEWS and r["text"]]
        rows.sort(key=lambda r: r["views"], reverse=True)
        kept = 0
        for r in rows[:PER_CHANNEL]:
            if r["videoId"] in seen: continue
            seen.add(r["videoId"]); all_rows.append(r); kept += 1
        print(f"{c['name']} ({title}): {kept}")
        time.sleep(0.1)
    all_rows.sort(key=lambda r: r["views"], reverse=True)
    data = {"updated": time.strftime("%Y-%m-%d"), "minViews": MIN_VIEWS, "count": len(all_rows), "titles": all_rows}
    json.dump(data, open("titles.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"총 {len(all_rows)}개 → titles.json")

main()
