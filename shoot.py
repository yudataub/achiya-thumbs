"""Runs on GitHub's server (workflow shoot.yml): the first page of every Achiya material in todo.json -> ach/<id>.webp.

todo.json   = [{"id": "<achiya id>", "u": "<material page>"}, ...]   (written by catalog-kit/achiya_cloud.py at home)
failed.json = {"<id>": "<reason>"}   materials with no picture to take (no file on the page, old Word...): not tried again

ONE request at a time, with pauses: it is someone else's site, and six in parallel got us blocked (HTTP 429) on 2026-10-07.
A job may run 6 hours at most: after BUDGET minutes it saves and starts the workflow again for the rest.
"""
import io, json, os, re, subprocess, time, urllib.request, urllib.error
import pymupdf
from PIL import Image

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"
FILE = re.compile(r'https://achiyayeda\.org/wp-content/uploads/[^"\'\s<>]+\.(?:pdf|docx?|pptx?|jpe?g|png)', re.I)
BUDGET = 320 * 60
SAVE_EVERY = 40


def get(url):
    time.sleep(1.5)
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60).read(30_000_000)


def shoot(i, link):
    for attempt in range(6):
        try:
            m = FILE.search(get(link).decode("utf-8", "replace"))
            if not m: return "no file on the page"
            url = m.group(0); ext = url.rsplit(".", 1)[1].lower()
            if ext == "doc": return "old Word"
            data = get(url)
            if ext in ("jpg", "jpeg", "png"):
                im = Image.open(io.BytesIO(data)).convert("RGB")
            else:
                pix = pymupdf.open(stream=data, filetype=ext)[0].get_pixmap(dpi=60)
                im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            im.thumbnail((400, 520)); im.save(os.path.join("ach", i + ".webp"), "WEBP", quality=70)
            return "ok"
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(180 * (attempt + 1)); continue
            if e.code in (404, 410): return f"HTTP {e.code}"
            return None          # a passing server error: try again in the next run
        except Exception as e:
            return f"{type(e).__name__}"
    return None


def save(msg):
    subprocess.run(["git", "add", "ach", "failed.json"], check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0: return
    subprocess.run(["git", "commit", "-qm", msg], check=True)
    for _ in range(3):
        if subprocess.run(["git", "pull", "--rebase", "-q"]).returncode == 0 and subprocess.run(["git", "push", "-q"]).returncode == 0: return
        time.sleep(10)
    raise SystemExit("push failed")


def main():
    start = time.time()
    os.makedirs("ach", exist_ok=True)
    todo = json.load(open("todo.json", encoding="utf-8")) if os.path.exists("todo.json") else []
    failed = json.load(open("failed.json", encoding="utf-8")) if os.path.exists("failed.json") else {}
    pending = [t for t in todo if t["id"] not in failed and not os.path.exists(os.path.join("ach", t["id"] + ".webp"))]
    print(len(pending), "of", len(todo), "to take", flush=True)
    n = 0
    for t in pending:
        if time.time() - start > BUDGET: break
        r = shoot(t["id"], t["u"])
        print(t["id"], r, flush=True)
        if r and r != "ok": failed[t["id"]] = r
        n += 1
        if n % SAVE_EVERY == 0:
            json.dump(failed, open("failed.json", "w", encoding="utf-8"), indent=0, sort_keys=True)
            save(f"Achiya pictures: {n} of {len(pending)}")
        time.sleep(4)
    json.dump(failed, open("failed.json", "w", encoding="utf-8"), indent=0, sort_keys=True)
    save(f"Achiya pictures: {n} taken or tried")
    left = [t for t in pending[n:]]
    if left:
        print(len(left), "left: starting the workflow again", flush=True)
        subprocess.run(["gh", "workflow", "run", "shoot.yml"], check=True)


if __name__ == "__main__":
    main()
