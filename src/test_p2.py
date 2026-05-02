"""Test Problem 2: All workshops with Crew 1 only."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import DataLoader
from preprocessing import Preprocessor
from solver_p2 import solve_problem_2, validate_problem_2, export_q2_schedule
from time_utils import format_seconds
from collections import defaultdict


def main():
    print("="*60)
    print("Problem 2: 所有车间 + 班组1设备")
    print("="*60)

    # Load data
    excel_path = '2026-51MCM-Problem B/B-attachment.xlsx'
    print(f"\n读取文件: {excel_path}")

    loader = DataLoader(excel_path)
    loader.load_all()

    # Preprocess
    preprocessor = Preprocessor(loader.processes, loader.equipment)
    preprocessor.preprocess()

    print(f"展开后工序数: {len(preprocessor.expanded_processes)}")
    print(f"班组1设备数: {len([e for e in preprocessor.equipment if e.crew == 1])}")

    # Print C workshop expansion order
    print("\nC车间展开顺序:")
    c_procs = [p for p in preprocessor.expanded_processes if p.workshop == 'C']
    print(f"  {' → '.join([p.expanded_id for p in c_procs])}")

    # Print all workshop orders
    print("\n各车间工序顺序:")
    for ws in ['A', 'B', 'C', 'D', 'E']:
        procs = preprocessor.process_order_within_workshop.get(ws, [])
        print(f"  Workshop {ws}: {' → '.join(procs)}")

    # Solve Problem 2
    print("\n求解中...")
    result = solve_problem_2(preprocessor, distance_func=loader.get_distance)

    # Build process-level times
    process_times = defaultdict(lambda: {"start": float('inf'), "end": 0})
    for op in result.operations:
        pid = op.process.expanded_id
        process_times[pid]["start"] = min(process_times[pid]["start"], op.start_time)
        process_times[pid]["end"] = max(process_times[pid]["end"], op.end_time)

    # Print each process aggregated start/end
    print("\n各工序聚合后的 start/end:")
    for pid in sorted(process_times.keys()):
        info = process_times[pid]
        print(f"  {pid}: start={info['start']}, end={info['end']}, duration={info['end']-info['start']}")

    print(f"\n结果:")
    print(f"  完成时间: {result.makespan} 秒")
    print(f"  格式: {format_seconds(result.makespan)}")
    print(f"  作业数: {len(result.operations)}")

    # Validate
    print("\n校验:")
    is_valid, errors = validate_problem_2(result, preprocessor)
    if is_valid:
        print("  ✓ 校验通过")
    else:
        print("  ✗ 校验失败:")
        for err in errors[:10]:
            print(f"    - {err}")
        if len(errors) > 10:
            print(f"    ... 还有 {len(errors) - 10} 个错误")

    # Print schedule by workshop
    print("\n作业排程 (按车间分组):")
    by_workshop = defaultdict(list)
    for op in result.operations:
        by_workshop[op.process.workshop].append(op)

    for ws in ['A', 'B', 'C', 'D', 'E']:
        if ws not in by_workshop:
            continue
        print(f"\n--- Workshop {ws} ---")
        print(f"{'设备编号':<35} {'起始时间':<10} {'结束时间':<10} {'时长(s)':<8} {'工序'}")
        print("-" * 80)
        for op in sorted(by_workshop[ws], key=lambda x: x.start_time):
            print(f"{op.equipment.equipment_id:<35} {op.start_time:<10} {op.end_time:<10} {op.duration:<8} {op.process.expanded_id}")

    # Export
    export_q2_schedule(result, 'outputs/q2_schedule.csv')

    print(f"\n最短完成时长: {result.makespan} 秒 ({format_seconds(result.makespan)})")

    return result


if __name__ == "__main__":
    main()