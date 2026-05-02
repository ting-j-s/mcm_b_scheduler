"""Main test entry point for MCM B scheduler - Data Loading & Preprocessing Only."""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import DataLoader
from preprocessing import Preprocessor
from time_utils import calculate_processing_time, format_seconds


def main():
    """Main entry point for data loading and preprocessing test."""
    print("="*60)
    print("MCM B Scheduler - 数据加载与预处理测试")
    print("="*60)

    # Find the Excel file
    excel_path = '../2026-51MCM-Problem B/B-attachment.xlsx'
    if not os.path.exists(excel_path):
        excel_path = '2026-51MCM-Problem B/B-attachment.xlsx'
    if not os.path.exists(excel_path):
        excel_path = '/data/xjr/mcm_b_scheduler/2026-51MCM-Problem B/B-attachment.xlsx'

    print(f"\n读取文件: {excel_path}")

    # Load data
    print("\n" + "="*60)
    print("1. 加载数据")
    print("="*60)

    loader = DataLoader(excel_path)
    loader.load_all()

    print(f"\n原始工序数: {len(loader.processes)}")
    print(f"设备总数: {len(loader.equipment)}")
    print(f"距离记录数: {len(loader.distances.distances)}")

    # Print process details
    print("\n" + "="*60)
    print("2. 工序详情")
    print("="*60)

    print("\n工序列表:")
    current_workshop = None
    for proc in loader.processes:
        if proc.workshop != current_workshop:
            print(f"\n--- Workshop {proc.workshop} ---")
            current_workshop = proc.workshop

        req_str = ", ".join([
            f"{r.equipment_type.name}({r.efficiency}m³/h)"
            for r in proc.requirements
        ])
        print(f"  {proc.process_id}: workload={proc.workload}m³, 设备=[{req_str}]")

    # Print equipment details
    print("\n" + "="*60)
    print("3. 设备详情")
    print("="*60)

    for crew in [1, 2]:
        print(f"\nCrew {crew}:")
        crew_eq = [e for e in loader.equipment if e.crew == crew]
        by_type = {}
        for eq in crew_eq:
            if eq.equipment_type not in by_type:
                by_type[eq.equipment_type] = []
            by_type[eq.equipment_type].append(eq)

        for etype, eqs in by_type.items():
            print(f"  {etype.name}: {len(eqs)} 台")
            for eq in eqs:
                print(f"    - {eq.equipment_id}")

    # Print distance matrix
    print("\n" + "="*60)
    print("4. 距离矩阵")
    print("="*60)
    loader.distances.print_matrix()

    # Preprocess
    print("\n" + "="*60)
    print("5. 预处理 (C车间C3-C5展开)")
    print("="*60)

    preprocessor = Preprocessor(loader.processes, loader.equipment)
    preprocessor.preprocess()

    print(f"\n原始工序数: {len(preprocessor.processes)}")
    print(f"展开后工序数: {len(preprocessor.expanded_processes)}")
    print(f"优先约束边数: {len(preprocessor.precedence_edges)}")

    # Show expanded C workshop
    print("\nC车间展开后工序:")
    c_procs = [p for p in preprocessor.expanded_processes if p.workshop == 'C']
    for p in c_procs:
        print(f"  {p.expanded_id}: workload={p.workload}m³")

    # Show precedence edges
    print("\n优先约束 (Workshop内按顺序):")
    for edge in preprocessor.precedence_edges:
        print(f"  {edge.from_process} -> {edge.to_process} (在{edge.workshop}车间)")

    # Calculate processing times
    print("\n" + "="*60)
    print("6. 作业时间计算")
    print("="*60)
    print("\n各工序作业时间 (秒):")
    print(f"{'工序ID':<20} {'工程量(m³)':<12} {'效率(m³/h)':<15} {'作业时间(s)':<12} {'HH:MM:SS'}")
    print("-" * 80)

    for proc in preprocessor.expanded_processes[:10]:  # Show first 10
        for req in proc.requirements:
            proc_time = calculate_processing_time(proc.workload, req.efficiency)
            print(f"{proc.expanded_id:<20} {proc.workload:<12.0f} {req.efficiency:<15.0f} {proc_time:<12} {format_seconds(proc_time)}")

    if len(preprocessor.expanded_processes) > 10:
        print(f"  ... 还有 {len(preprocessor.expanded_processes) - 10} 道工序")

    # Summary
    print("\n" + "="*60)
    print("摘要")
    print("="*60)
    preprocessor.print_summary()

    print("\n" + "="*60)
    print("测试完成!")
    print("="*60)


if __name__ == "__main__":
    main()