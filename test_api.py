import sys, subprocess
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
r = subprocess.run(["python", "evaluate_stocks.py"], capture_output=True, text=True, encoding="utf-8")
open("result.txt", "w", encoding="utf-8").write(r.stdout + (r.stderr or ""))
print(r.stdout)
if r.stderr:
    print("ERR:", r.stderr[:500])
