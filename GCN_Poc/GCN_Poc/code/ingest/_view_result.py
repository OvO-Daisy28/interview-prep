"""查看 native_r1.json 关键统计（容器内跑，避免 PowerShell 引号问题）。"""
import json, sys

path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/native_r1.json"
d = json.load(open(path))
print("=== KEY METRICS ===")
print("label:", d.get("label"))
print("upload_seconds:", d.get("upload_seconds"))
print("parse_wall_seconds:", d.get("parse_wall_seconds"))
print("succeeded:", d.get("succeeded"))
print("failed:", d.get("failed"))
print("cancelled:", d.get("cancelled"))
print("throughput:", d.get("throughput"))
print("samples count:", len(d.get("progress_samples", [])))
print("msg_samples count:", len(d.get("msg_samples", [])))
print()
print("=== FIRST 5 PROGRESS SAMPLES ===")
for s in d.get("progress_samples", [])[:5]:
    print(f"  wall={s.get('wall')} done={s.get('done')} fail={s.get('fail')} "
          f"running={s.get('running')} unstart={s.get('unstart')} "
          f"overall={s.get('overall_pct')}")
print()
print("=== LAST 5 PROGRESS SAMPLES ===")
for s in d.get("progress_samples", [])[-5:]:
    print(f"  wall={s.get('wall')} done={s.get('done')} fail={s.get('fail')} "
          f"running={s.get('running')} unstart={s.get('unstart')} "
          f"overall={s.get('overall_pct')}")
print()
print("=== FAIL DETAILS (first 5) ===")
for f in d.get("fail_details", [])[:5]:
    print(f"  {f.get('name')}: {f.get('msg','')[:100]}")
