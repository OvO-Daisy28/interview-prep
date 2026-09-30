"""挖 native_r1.json 的进度可见性证据：progress_msg 文本样本 + process_duration 变化。"""
import json

d = json.load(open("/tmp/native_r1.json"))

print("=== MSG SAMPLES (progress_msg 文本，方案A 进度可见性证据) ===")
print(f"共 {len(d.get('msg_samples', []))} 条 msg 样本\n")
seen_msgs = set()
for m in d.get("msg_samples", []):
    msg = m.get("msg", "")
    # 去重，只看不同的 msg
    if msg and msg not in seen_msgs:
        seen_msgs.add(msg)
        print(f"  wall={m.get('wall')}s prog={m.get('prog')} dur={m.get('dur')}s")
        print(f"    msg: {msg[:200]}")
        print()

print(f"=== 去重后不同的 progress_msg 共 {len(seen_msgs)} 种 ===")
print()

print("=== PROGRESS SAMPLES 进度爬升轨迹（每 50 条取 1 条）===")
samples = d.get("progress_samples", [])
step = max(1, len(samples) // 20)
for s in samples[::step]:
    # 看运行中文档的 dur 范围
    durs = [rm.get("dur", 0) for rm in s.get("running_msgs", [])]
    max_dur = max(durs) if durs else 0
    print(f"  wall={s.get('wall')}s done={s.get('done')} running={s.get('running')} "
          f"overall={s.get('overall_pct')}% max_dur={max_dur:.1f}s")
