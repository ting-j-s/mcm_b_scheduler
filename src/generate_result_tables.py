"""Generate result_tables.xlsx and final_summary.txt from solver outputs."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import DataLoader
from preprocessing import Preprocessor
from solver_p1 import solve_problem_1, validate_problem_1
from solver_p2 import solve_problem_2, validate_problem_2
from solver_p3 import solve_problem_3, validate_problem_3
from solver_p4 import solve_problem_4, validate_problem_4
from time_utils import format_seconds
from models import EquipmentType

import pandas as pd
import csv


def run_solvers():
    """Run all solvers and return results + validation status."""
    excel_path = '2026-51MCM-Problem B/B-attachment.xlsx'
    loader = DataLoader(excel_path)
    loader.load_all()

    preprocessor = Preprocessor(loader.processes, loader.equipment)
    preprocessor.preprocess()

    results = {}
    validations = {}

    # P1
    r1 = solve_problem_1(preprocessor, distance_func=loader.get_distance)
    v1, e1 = validate_problem_1(r1, preprocessor, distance_func=loader.get_distance)
    results['p1'] = {'result': r1, 'purchases': None, 'total_cost': None}
    validations['p1'] = v1

    # P2
    r2 = solve_problem_2(preprocessor, distance_func=loader.get_distance)
    v2, e2 = validate_problem_2(r2, preprocessor, distance_func=loader.get_distance)
    results['p2'] = {'result': r2, 'purchases': None, 'total_cost': None}
    validations['p2'] = v2

    # P3
    r3 = solve_problem_3(preprocessor, distance_func=loader.get_distance)
    v3, e3 = validate_problem_3(r3, preprocessor, distance_func=loader.get_distance)
    results['p3'] = {'result': r3, 'purchases': None, 'total_cost': None}
    validations['p3'] = v3

    # P4
    r4, purchases, total_cost = solve_problem_4(
        preprocessor, distance_func=loader.get_distance,
        unit_prices=loader.unit_prices, budget=500000.0
    )
    v4, e4 = validate_problem_4(r4, purchases, total_cost, preprocessor, loader.unit_prices, budget=500000.0, distance_func=loader.get_distance)
    results['p4'] = {'result': r4, 'purchases': purchases, 'total_cost': total_cost}
    validations['p4'] = v4

    return results, validations, loader.unit_prices


def export_schedule(result, path, fields, crew_col=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rows = []
    for i, op in enumerate(sorted(result.operations, key=lambda x: x.start_time), 1):
        row = {
            '序号': i,
            '设备编号': op.equipment.equipment_id,
            '起始时间': op.start_time,
            '结束时间': op.end_time,
            '持续工作时间(s)': op.duration,
            '工序编号': op.process.expanded_id
        }
        if crew_col:
            row['班组'] = op.equipment.crew
        rows.append(row)
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def export_purchase(purchases, unit_prices, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    type_names = {
        EquipmentType.AUTOMATED_CONVEYING_ARM: '自动化输送臂',
        EquipmentType.INDUSTRIAL_CLEANING_MACHINE: '工业清洗机',
        EquipmentType.PRECISION_FILLING_MACHINE: '精密灌装机',
        EquipmentType.AUTOMATIC_SENSING_MULTI_FUNCTION_MACHINE: '自动传感多功能机',
        EquipmentType.HIGH_SPEED_POLISHING_MACHINE: '高速抛光机',
    }
    rows = []
    for et in EquipmentType:
        rows.append({
            '设备名称': type_names.get(et, et.name),
            '班组1购买台数': purchases.get((et, 1), 0),
            '班组2购买台数': purchases.get((et, 2), 0)
        })
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['设备名称', '班组1购买台数', '班组2购买台数'])
        writer.writeheader()
        writer.writerows(rows)


def make_excel(results, validations, unit_prices):
    """Generate result_tables.xlsx."""
    writer = pd.ExcelWriter('outputs/result_tables.xlsx', engine='openpyxl')

    # Table 1
    r1 = results['p1']['result']
    rows1 = []
    for i, op in enumerate(sorted(r1.operations, key=lambda x: x.start_time), 1):
        rows1.append({
            '序号': i, '设备编号': op.equipment.equipment_id,
            '起始时间': op.start_time, '结束时间': op.end_time,
            '持续工作时间(s)': op.duration, '工序编号': op.process.expanded_id
        })
    df1 = pd.DataFrame(rows1, columns=['序号', '设备编号', '起始时间', '结束时间', '持续工作时间(s)', '工序编号'])
    df1.to_excel(writer, sheet_name='Table1_Problem1', index=False)

    # Table 2
    r2 = results['p2']['result']
    rows2 = []
    for i, op in enumerate(sorted(r2.operations, key=lambda x: x.start_time), 1):
        rows2.append({
            '序号': i, '设备编号': op.equipment.equipment_id,
            '起始时间': op.start_time, '结束时间': op.end_time,
            '持续工作时间(s)': op.duration, '工序编号': op.process.expanded_id
        })
    df2 = pd.DataFrame(rows2, columns=['序号', '设备编号', '起始时间', '结束时间', '持续工作时间(s)', '工序编号'])
    df2.to_excel(writer, sheet_name='Table2_Problem2', index=False)

    # Table 3
    r3 = results['p3']['result']
    rows3 = []
    for i, op in enumerate(sorted(r3.operations, key=lambda x: x.start_time), 1):
        rows3.append({
            '序号': i, '设备编号': op.equipment.equipment_id,
            '起始时间': op.start_time, '结束时间': op.end_time,
            '持续工作时间(s)': op.duration, '工序编号': op.process.expanded_id,
            '班组': op.equipment.crew
        })
    df3 = pd.DataFrame(rows3, columns=['序号', '设备编号', '起始时间', '结束时间', '持续工作时间(s)', '工序编号', '班组'])
    df3.to_excel(writer, sheet_name='Table3_Problem3', index=False)

    # Table 4
    r4 = results['p4']['result']
    rows4 = []
    for i, op in enumerate(sorted(r4.operations, key=lambda x: x.start_time), 1):
        rows4.append({
            '序号': i, '设备编号': op.equipment.equipment_id,
            '起始时间': op.start_time, '结束时间': op.end_time,
            '持续工作时间(s)': op.duration, '工序编号': op.process.expanded_id,
            '班组': op.equipment.crew
        })
    df4 = pd.DataFrame(rows4, columns=['序号', '设备编号', '起始时间', '结束时间', '持续工作时间(s)', '工序编号', '班组'])
    df4.to_excel(writer, sheet_name='Table4_Problem4', index=False)

    # Table 5
    purchases = results['p4']['purchases']
    type_names = {
        EquipmentType.AUTOMATED_CONVEYING_ARM: '自动化输送臂',
        EquipmentType.INDUSTRIAL_CLEANING_MACHINE: '工业清洗机',
        EquipmentType.PRECISION_FILLING_MACHINE: '精密灌装机',
        EquipmentType.AUTOMATIC_SENSING_MULTI_FUNCTION_MACHINE: '自动传感多功能机',
        EquipmentType.HIGH_SPEED_POLISHING_MACHINE: '高速抛光机',
    }
    rows5 = []
    for et in EquipmentType:
        rows5.append({
            '设备名称': type_names.get(et, et.name),
            '班组1购买台数': purchases.get((et, 1), 0),
            '班组2购买台数': purchases.get((et, 2), 0)
        })
    df5 = pd.DataFrame(rows5, columns=['设备名称', '班组1购买台数', '班组2购买台数'])
    df5.to_excel(writer, sheet_name='Table5_Purchase', index=False)

    # Summary
    summary = [
        {'问题': 'Problem 1', '使用资源': 'A车间/班组1', '是否允许采购': '否',
         '最短完成时间(s)': r1.makespan, 'HH:MM:SS': format_seconds(r1.makespan),
         '校验状态': '通过' if validations['p1'] else '失败', '备注': '仅A车间3工序'},
        {'问题': 'Problem 2', '使用资源': 'A-E车间/班组1', '是否允许采购': '否',
         '最短完成时间(s)': r2.makespan, 'HH:MM:SS': format_seconds(r2.makespan),
         '校验状态': '通过' if validations['p2'] else '失败', '备注': '全车间班组1'},
        {'问题': 'Problem 3', '使用资源': 'A-E车间/班组1+2', '是否允许采购': '否',
         '最短完成时间(s)': r3.makespan, 'HH:MM:SS': format_seconds(r3.makespan),
         '校验状态': '通过' if validations['p3'] else '失败', '备注': '双班组协同'},
        {'问题': 'Problem 4', '使用资源': 'A-E车间/班组1+2+新购', '是否允许采购': '是',
         '最短完成时间(s)': r4.makespan, 'HH:MM:SS': format_seconds(r4.makespan),
         '校验状态': '通过' if validations['p4'] else '失败',
         '备注': f"采购费用{int(results['p4']['total_cost'])}/500000"},
    ]
    df_sum = pd.DataFrame(summary)
    df_sum.to_excel(writer, sheet_name='Summary', index=False)

    writer.close()


def make_summary_txt(results, validations):
    """Generate final_summary.txt."""
    r1, r2, r3, r4 = results['p1']['result'], results['p2']['result'], results['p3']['result'], results['p4']['result']
    purchases = results['p4']['purchases']
    total_cost = results['p4']['total_cost']

    all_pass = all(validations.values())

    lines = [
        "=" * 50,
        "MCM B Scheduler 最终结果摘要",
        "=" * 50,
        f"Q1 makespan: {r1.makespan} 秒 ({format_seconds(r1.makespan)})",
        f"Q2 makespan: {r2.makespan} 秒 ({format_seconds(r2.makespan)})",
        f"Q3 makespan: {r3.makespan} 秒 ({format_seconds(r3.makespan)})",
        f"Q4 makespan: {r4.makespan} 秒 ({format_seconds(r4.makespan)})",
        f"Q4 purchase cost: {int(total_cost)} 元",
        "",
        "校验状态:",
        f"  Problem 1: {'通过' if validations['p1'] else '失败'}",
        f"  Problem 2: {'通过' if validations['p2'] else '失败'}",
        f"  Problem 3: {'通过' if validations['p3'] else '失败'}",
        f"  Problem 4: {'通过' if validations['p4'] else '失败'}",
        "",
        f"所有校验通过: {'是' if all_pass else '否'}",
    ]

    os.makedirs('outputs', exist_ok=True)
    with open('outputs/final_summary.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print("导出: outputs/final_summary.txt")


if __name__ == '__main__':
    print("运行所有求解器...")
    results, validations, unit_prices = run_solvers()

    print("\n生成 Excel...")
    make_excel(results, validations, unit_prices)
    print("导出: outputs/result_tables.xlsx")

    make_summary_txt(results, validations)

    print("\n最终摘要:")
    print(f"  P1: {results['p1']['result'].makespan} 秒")
    print(f"  P2: {results['p2']['result'].makespan} 秒")
    print(f"  P3: {results['p3']['result'].makespan} 秒")
    print(f"  P4: {results['p4']['result'].makespan} 秒, 采购 {int(results['p4']['total_cost'])} 元")
    print(f"  校验: P1={'通过' if validations['p1'] else '失败'}, P2={'通过' if validations['p2'] else '失败'}, P3={'通过' if validations['p3'] else '失败'}, P4={'通过' if validations['p4'] else '失败'}")