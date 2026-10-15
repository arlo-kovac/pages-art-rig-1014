import json, os, ssl, sys, time, urllib.request, urllib.error
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
    s,b=http(f"{API}/repos/{REPO}/git/commits","POST",{"message":f"s6-{tag}-{RUN}","tree":tree,"parents":[parent]})
    try: new=json.loads(b)["sha"]
    except Exception: return None
    http(f"{API}/repos/{REPO}/git/refs/heads/main","PATCH",{"sha":new,"force":False})
    return new

print("=== ARMS6-START ===",flush=True)
try:
    if not ART: print("🔴 ARMING GATE FAILED: no artifact id.",flush=True); sys.exit(0)
    # THE OPERATION'S TITULAR QUESTION: is artifact_id bound to the RUN, the REPO, or the OWNER?
    PLAN=[("A_thisrun",   int(ART),      "artifact uploaded by THIS run  <- POSITIVE CONTROL"),
          ("B_priorrun",  11930831882,   "SAME repo, a PRIOR run"),
          ("C_otherrepo", 11929918945,   "SAME owner, DIFFERENT repo (arlo/ghnet-netpos-1014)"),
          ("D_otherowner",10910066574,   "DIFFERENT owner, public repo (mr-benty/zzq-bf45-capture)"),
          ("E_nonexistent",999999999,    "an id that does not exist  <- NEGATIVE CONTROL")]
    rows=[]
    for tag,aid,why in PLAN:
        tok=mint()
        if len(tok)<20: print(f"  {tag}: 🔴 OIDC VOID",flush=True); rows.append((tag,"OIDC-VOID","",why)); continue
        bver=mkcommit(tag)
        if not bver: print(f"  {tag}: 🔴 COMMIT VOID",flush=True); rows.append((tag,"COMMIT-VOID","",why)); continue
        s,b=http(f"{API}/repos/{REPO}/pages/deployments","POST",
                 {"pages_build_version":bver,"oidc_token":tok,"artifact_id":aid})
        msg=""
        try: j=json.loads(b); msg=j.get("message","") or ("created id="+str(j.get("id",""))[:12])
        except Exception: msg=" ".join(b.split())[:90]
        did=None
        try: did=json.loads(b).get("id")
        except Exception: pass
        rows.append((tag,str(s),msg[:95],why))
        print(f"  {tag:<14} id={aid:<12} -> {s:<4} {msg[:95]}",flush=True)
        if did:
            time.sleep(4); http(f"{API}/repos/{REPO}/pages/deployments/{did}/cancel","POST",{})
        time.sleep(3)

    print("\n=== GATES, derived from the two controls ===",flush=True)
    A=[r for r in rows if r[0]=="A_thisrun"][0]
    E=[r for r in rows if r[0]=="E_nonexistent"][0]
    print(f"  POSITIVE control (this run's artifact)  -> {A[1]}",flush=True)
    print(f"  NEGATIVE control (nonexistent id)       -> {E[1]} {E[2]}",flush=True)
    if not A[1].startswith("2"):
        print("🔴 VOID: the positive control did not create a deployment. Nothing below is "
              "attributable -- same defect class as runs 38692481202 / my 10-14 arms.",flush=True)
    elif E[1].startswith("2"):
        print("🔴 VOID: the NEGATIVE control succeeded, so artifact_id is not being resolved at "
              "all and no binding conclusion is possible.",flush=True)
    else:
        print("✅ BOTH CONTROLS FIRED. Foreign-artifact results are attributable:",flush=True)
        for tag,st,msg,why in rows:
            if tag in ("B_priorrun","C_otherrepo","D_otherowner"):
                print(f"     {tag:<14} {st:<5} {msg[:70]:<70} [{why}]",flush=True)
        print("\n  READ: a foreign id answering IDENTICALLY to the NONEXISTENT control means the "
              "id is scoped and the foreign artifact is not representable here. A foreign id "
              "answering like the POSITIVE control means it resolved -- that is the crossing.",flush=True)
finally:
    print("=== ARMS6-END ===",flush=True)
