"""Test Problem 1: Workshop A with Crew 1 only."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import DataLoader
from preprocessing import Preprocessor
from solver_p1 import solve_problem_1, validate_problem_1, export_q1_schedule
from time_utils import format_seconds


def main():
    print("="*60)
    print("Problem 1: A车间 + 班组1设备")
    print("="*60)

    # Load data
    excel_path = '2026-51MCM-Problem B/B-attachment.xlsx'
    print(f"\n读取文件: {excel_path}")

    loader = DataLoader(excel_path)
    loader.load_all()
    print(f"设备总数: {len(loader.equipment)}")

    # Preprocess
    preprocessor = Preprocessor(loader.processes, loader.equipment)
    preprocessor.preprocess()

    # Filter check
    a_procs = [p for p in preprocessor.expanded_processes if p.workshop == 'A']
    crew1_eq = [e for e in preprocessor.equipment if e.crew == 1]
    print(f"A车间工序数: {len(a_procs)}")
    print(f"班组1设备数: {len(crew1_eq)}")

    # Solve Problem 1
    print("\n求解中...")
    result = solve_problem_1(preprocessor, distance_func=loader.get_distance)

    print(f"\n结果:")
    print(f"  完成时间: {result.makespan} 秒")
    print(f"  格式: {format_seconds(result.makespan)}")
    print(f"  作业数: {len(result.operations)}")

    # Validate
    print("\n校验:")
    is_valid, errors = validate_problem_1(result, preprocessor, distance_func=loader.get_distance)
    if is_valid:
        print("  ✓ 校验通过")
    else:
        print("  ✗ 校验失败:")
        for err in errors:
            print(f"    - {err}")

    # Print schedule
    print("\n作业排程:")
    print(f"{'序号':<4} {'设备编号':<15} {'起始时间':<10} {'结束时间':<10} {'时长(s)':<8} {'工序'}")
    print("-" * 70)
    for i, op in enumerate(sorted(result.operations, key=lambda x: x.start_time), 1):
        print(f"{i:<4} {op.equipment.equipment_id:<15} {op.start_time:<10} {op.end_time:<10} {op.duration:<8} {op.process.expanded_id}")

    # Export
    export_q1_schedule(result, 'outputs/q1_schedule.csv')

    print(f"\n最短完成时长: {result.makespan} 秒 ({format_seconds(result.makespan)})")

    return result


if __name__ == "__main__":
    main()