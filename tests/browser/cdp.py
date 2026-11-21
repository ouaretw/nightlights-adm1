"""Minimal Chrome DevTools Protocol driver for headless Edge (no external deps but websocket-client)."""
import base64, json, os, subprocess, tempfile, time, urllib.request
import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


class Browser:
    def __init__(self, port=9333):
        self.port = port
        self.prof = tempfile.mkdtemp(prefix="edgecdp_")
        self.proc = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", f"--remote-debugging-port={port}",
                                      f"--user-data-dir={self.prof}", "--no-first-run", "--hide-scrollbars", "about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
                page = [t for t in tabs if t["type"] == "page"][0]
                break
            except Exception:
                time.sleep(0.25)
        self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=60, suppress_origin=True)
        self.i = 0
        self.events = []
        for m in ("Page.enable", "Runtime.enable", "Log.enable"):
            self.send(m)

    def send(self, method, **params):
        self.i += 1
        my = self.i
        self.ws.send(json.dumps({"id": my, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == my:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})
            self.events.append(msg)

    def errors(self, clear=True):
        out = []
        for e in self.events:
            m = e.get("method")
            if m == "Runtime.exceptionThrown":
                d = e["params"]["exceptionDetails"]
                out.append("EXC " + (d.get("exception", {}).get("description") or d.get("text", ""))[:300])
            elif m == "Runtime.consoleAPICalled" and e["params"]["type"] in ("error", "assert"):
                out.append("CONSOLE " + " ".join(str(a.get("value", a.get("description", ""))) for a in e["params"]["args"])[:300])
            elif m == "Log.entryAdded" and e["params"]["entry"]["level"] == "error":
                out.append("LOG " + e["params"]["entry"]["text"][:200] + " " + e["params"]["entry"].get("url", ""))
        if clear:
            self.events = []
        return out

    def viewport(self, w, h, mobile=False):
        self.send("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=mobile)

    def goto(self, url, wait_js="document.readyState==='complete'", timeout=40):
        self.send("Page.navigate", url=url)
        time.sleep(0.3)
        return self.wait(wait_js, timeout)

    def js(self, expr, await_promise=True):
        r = self.send("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=await_promise)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"].get("exception", {}).get("description", r["exceptionDetails"]))
        return r.get("result", {}).get("value")

    def wait(self, expr, timeout=40):
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                if self.js(f"!!({expr})"):
                    return True
            except Exception:
                pass
            time.sleep(0.25)
        return False

    def shot(self, path, full=True):
        if full:
            h = self.js("Math.ceil(document.documentElement.scrollHeight)")
            w = self.js("window.innerWidth")
            r = self.send("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                          clip={"x": 0, "y": 0, "width": w, "height": min(h, 6000), "scale": 1})
        else:
            r = self.send("Page.captureScreenshot", format="png")
        with open(path, "wb") as f:
            f.write(base64.b64decode(r["data"]))

    def close(self):
        try:
            self.ws.close()
        finally:
            self.proc.kill()
