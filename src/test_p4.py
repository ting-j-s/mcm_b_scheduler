"""Test Problem 4: Budget-constrained equipment purchase and scheduling."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import DataLoader
from preprocessing import Preprocessor
from solver_p4 import (
    solve_problem_4, validate_problem_4,
    export_q4_schedule, export_q4_purchase
)
from models import EquipmentType
from time_utils import format_seconds


def main():
    print("="*60)
    print("Problem 4: 预算约束下的设备购买与调度优化")
    print("="*60)

    excel_path = '2026-51MCM-Problem B/B-attachment.xlsx'
    print(f"\n读取文件: {excel_path}")

    loader = DataLoader(excel_path)
    loader.load_all()

    preprocessor = Preprocessor(loader.processes, loader.equipment)
    preprocessor.preprocess()

    print(f"展开后工序数: {len(preprocessor.expanded_processes)}")
    print(f"现有设备总数: {len(preprocessor.equipment)}")
    print(f"预算上限: 500000 元")

    print("\n求解中...")
    result, purchases, total_cost = solve_problem_4(
        preprocessor,
        distance_func=loader.get_distance,
        unit_prices=loader.unit_prices,
        budget=500000.0
    )

    print(f"\n结果:")
    print(f"  完成时间: {result.makespan} 秒")
    print(f"  格式: {format_seconds(result.makespan)}")
    print(f"  作业数: {len(result.operations)}")
    print(f"  购买总费用: {total_cost:.0f} 元")

    # Validate
    print("\n校验:")
    is_valid, errors = validate_problem_4(
        result, purchases, total_cost,
        preprocessor, loader.unit_prices, budget=500000.0
    )
    if is_valid:
        print("  ✓ 校验通过")
    else:
        print("  ✗ 校验失败:")
        for err in errors[:10]:
            print(f"    - {err}")
        if len(errors) > 10:
            print(f"    ... 还有 {len(errors) - 10} 个错误")

    # Print purchase plan
    print("\n购买方案:")
    print(f"{'设备类型':<30} {'班组1':<10} {'班组2':<10}")
    print("-" * 50)
    et_names = {
        EquipmentType.AUTOMATED_CONVEYING_ARM: '自动化输送臂',
        EquipmentType.INDUSTRIAL_CLEANING_MACHINE: '工业清洗机',
        EquipmentType.PRECISION_FILLING_MACHINE: '精密灌装机',
        EquipmentType.AUTOMATIC_SENSING_MULTI_FUNCTION_MACHINE: '自动传感多功能机',
        EquipmentType.HIGH_SPEED_POLISHING_MACHINE: '高速抛光机',
    }
    for et in EquipmentType:
        crew1 = purchases.get((et, 1), 0)
        crew2 = purchases.get((et, 2), 0)
        if crew1 > 0 or crew2 > 0:
            print(f"  {et_names.get(et, et.name):<28} 班组1: {crew1} 台  班组2: {crew2} 台")

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
        print(f"{'设备编号':<35} {'班组':<6} {'起始时间':<10} {'结束时间':<10} {'工序'}")
        print("-" * 85)
        for op in sorted(by_workshop[ws], key=lambda x: x.start_time):
            print(f"{op.equipment.equipment_id:<35} {op.equipment.crew:<6} {op.start_time:<10} {op.end_time:<10} {op.process.expanded_id}")

    # Export
    export_q4_schedule(result, 'outputs/q4_schedule.csv')
    export_q4_purchase(purchases, loader.unit_prices, 'outputs/q4_purchase.csv')

    print(f"\n最短完成时长: {result.makespan} 秒 ({format_seconds(result.makespan)})")
    print(f"购买总费用: {total_cost:.0f} 元 (预算 500000 元)")

    return result, purchases, total_cost


if __name__ == "__main__":
    main()