"""Test Problem 3: All workshops with Crew 1 + Crew 2 equipment."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import DataLoader
from preprocessing import Preprocessor
from solver_p3 import solve_problem_3, validate_problem_3, export_q3_schedule
from time_utils import format_seconds


def main():
    print("="*60)
    print("Problem 3: 所有车间 + 班组1 + 班组2 设备")
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
    print(f"班组2设备数: {len([e for e in preprocessor.equipment if e.crew == 2])}")

    # Solve Problem 3
    print("\n求解中...")
    result = solve_problem_3(preprocessor, distance_func=loader.get_distance)

    print(f"\n结果:")
    print(f"  完成时间: {result.makespan} 秒")
    print(f"  格式: {format_seconds(result.makespan)}")
    print(f"  作业数: {len(result.operations)}")

    # Validate
    print("\n校验:")
    is_valid, errors = validate_problem_3(result, preprocessor)
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
    from collections import defaultdict
    by_workshop = defaultdict(list)
    for op in result.operations:
        by_workshop[op.process.workshop].append(op)

    for ws in ['A', 'B', 'C', 'D', 'E']:
        if ws not in by_workshop:
            continue
        print(f"\n--- Workshop {ws} ---")
        print(f"{'设备编号':<35} {'班组':<6} {'起始时间':<10} {'结束时间':<10} {'时长(s)':<8} {'工序'}")
        print("-" * 90)
        for op in sorted(by_workshop[ws], key=lambda x: x.start_time):
            print(f"{op.equipment.equipment_id:<35} {op.equipment.crew:<6} {op.start_time:<10} {op.end_time:<10} {op.duration:<8} {op.process.expanded_id}")

    # Export
    export_q3_schedule(result, 'outputs/q3_schedule.csv')

    print(f"\n最短完成时长: {result.makespan} 秒 ({format_seconds(result.makespan)})")

    # Summary by crew
    from collections import Counter
    crew_usage = Counter(op.equipment.crew for op in result.operations)
    print(f"\n设备使用统计:")
    for crew, count in sorted(crew_usage.items()):
        print(f"  班组{crew}: {count} 次")

    return result


if __name__ == "__main__":
    main()