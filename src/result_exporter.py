"""Result exporter module for MCM B scheduler."""

import os
from typing import List, Dict, Any
from datetime import datetime

import pandas as pd

from models import ScheduleResult, ScheduledOperation, Equipment, EquipmentType
from preprocessing import Preprocessor
from time_utils import format_seconds


class ResultExporter:
    """Exports scheduling results to CSV and Excel."""

    def __init__(self, preprocessor: Preprocessor, output_dir: str = "outputs"):
        self.preprocessor = preprocessor
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def export_schedule_csv(self, result: ScheduleResult, filename: str):
        """Export schedule to CSV file."""
        rows = []

        for op in result.operations:
            proc = op.process
            eq = op.equipment

            rows.append({
                'Process ID': proc.expanded_id(),
                'Workshop': proc.workshop,
                'Original Process ID': proc.original_id,
                'Equipment ID': eq.equipment_id,
                'Equipment Type': eq.equipment_type.value,
                'Crew': eq.crew,
                'Start Time (s)': op.start_time,
                'End Time (s)': op.end_time,
                'Duration (s)': op.duration,
                'Start Time (HH:MM:SS)': format_seconds(op.start_time),
                'End Time (HH:MM:SS)': format_seconds(op.end_time),
                'Transport Time (s)': op.transport_time,
                'Workload (m³)': proc.workload,
            })

            # Add efficiency info for each requirement
            for i, req in enumerate(proc.requirements):
                rows[-1][f'Required Type {i+1}'] = req.equipment_type.value
                rows[-1][f'Efficiency {i+1} (m³/h)'] = req.efficiency

        df = pd.DataFrame(rows)
        filepath = os.path.join(self.output_dir, filename)
        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        print(f"Exported schedule to {filepath}")
        return df

    def export_purchase_csv(
        self,
        purchased_equipment: List[Equipment],
        total_cost: float,
        filename: str = "q4_purchase.csv"
    ):
        """Export equipment purchase details to CSV."""
        rows = []

        for eq in purchased_equipment:
            rows.append({
                'Equipment ID': eq.equipment_id,
                'Equipment Type': eq.equipment_type.value,
                'Crew': eq.crew,
                'Speed (m/s)': eq.speed_mps,
                'Unit Price': eq.unit_price,
            })

        rows.append({
            'Equipment ID': 'TOTAL',
            'Equipment Type': '',
            'Crew': '',
            'Speed (m/s)': '',
            'Unit Price': total_cost,
        })

        df = pd.DataFrame(rows)
        filepath = os.path.join(self.output_dir, filename)
        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        print(f"Exported purchase details to {filepath}")
        return df

    def export_result_tables_excel(
        self,
        results: Dict[int, ScheduleResult],
        purchases: Dict[int, List[Equipment]],
        costs: Dict[int, float],
        filename: str = "result_tables.xlsx"
    ):
        """
        Export all result tables to a single Excel file with multiple sheets.

        Expected sheets:
        - Table 1: Problem 1 Schedule
        - Table 2: Problem 2 Schedule
        - Table 3: Problem 3 Schedule
        - Table 4: Problem 4 Schedule & Purchase
        - Summary: Overview of all results
        """
        filepath = os.path.join(self.output_dir, filename)

        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # Sheet 1-3: Problem schedules
            for q_num in [1, 2, 3]:
                if q_num in results:
                    df = self._create_schedule_dataframe(results[q_num])
                    sheet_name = f"Problem {q_num}"
                    df.to_excel(writer, sheet_name=sheet_name, index=False)

            # Sheet 4: Problem 4 (combined schedule + purchase)
            if 4 in results:
                # Schedule
                df_schedule = self._create_schedule_dataframe(results[4])
                df_schedule.to_excel(writer, sheet_name="Problem 4 Schedule", index=False)

                # Purchase
                if 4 in purchases:
                    df_purchase = self._create_purchase_dataframe(
                        purchases[4],
                        costs.get(4, 0.0)
                    )
                    df_purchase.to_excel(writer, sheet_name="Problem 4 Purchase", index=False)

            # Summary sheet
            summary_data = []
            for q_num, result in results.items():
                summary_data.append({
                    'Problem': f"Problem {q_num}",
                    'Makespan (s)': result.makespan,
                    'Makespan (HH:MM:SS)': format_seconds(result.makespan),
                    'Number of Operations': len(result.operations),
                    'Total Cost': costs.get(q_num, 0.0),
                })

            df_summary = pd.DataFrame(summary_data)
            df_summary.to_excel(writer, sheet_name="Summary", index=False)

        print(f"Exported result tables to {filepath}")
        return filepath

    def _create_schedule_dataframe(self, result: ScheduleResult) -> pd.DataFrame:
        """Create a DataFrame from a schedule result."""
        rows = []

        # Group operations by process
        process_ops: Dict[str, List[ScheduledOperation]] = {}
        for op in result.operations:
            proc_id = op.process.expanded_id()
            if proc_id not in process_ops:
                process_ops[proc_id] = []
            process_ops[proc_id].append(op)

        # For each process, create a row
        for proc_id, ops in process_ops.items():
            if not ops:
                continue

            # Get process info from first operation
            first_op = ops[0]
            proc = first_op.process

            # Get equipment info
            equipment_ids = [op.equipment.equipment_id for op in ops]
            equipment_types = [op.equipment.equipment_type.value for op in ops]
            crews = [op.equipment.crew for op in ops]

            # Calculate start/end times (all equipment must finish)
            start_times = [op.start_time for op in ops]
            end_times = [op.end_time for op in ops]

            # Process completion is when all equipment finish
            proc_start = min(start_times)
            proc_end = max(end_times)

            rows.append({
                'Process ID': proc_id,
                'Workshop': proc.workshop,
                'Equipment IDs': ', '.join(equipment_ids),
                'Equipment Types': ', '.join(equipment_types),
                'Crews': ', '.join(map(str, crews)),
                'Start Time (s)': proc_start,
                'End Time (s)': proc_end,
                'Duration (s)': proc_end - proc_start,
                'Start Time (HH:MM:SS)': format_seconds(proc_start),
                'End Time (HH:MM:SS)': format_seconds(proc_end),
                'Workload (m³)': proc.workload,
            })

        df = pd.DataFrame(rows)
        df = df.sort_values(['Workshop', 'Start Time (s)'])
        return df

    def _create_purchase_dataframe(
        self,
        purchased_equipment: List[Equipment],
        total_cost: float
    ) -> pd.DataFrame:
        """Create a DataFrame from purchased equipment."""
        rows = []

        for eq in purchased_equipment:
            rows.append({
                'Equipment ID': eq.equipment_id,
                'Equipment Type': eq.equipment_type.value,
                'Crew': eq.crew,
                'Speed (m/s)': eq.speed_mps,
                'Unit Price (yuan)': eq.unit_price,
            })

        # Add total row
        if rows:
            rows.append({
                'Equipment ID': 'TOTAL',
                'Equipment Type': '',
                'Crew': '',
                'Speed (m/s)': '',
                'Unit Price (yuan)': total_cost,
            })

        return pd.DataFrame(rows)

    def print_summary(self, result: ScheduleResult, problem_name: str = ""):
        """Print a human-readable summary of the result."""
        print(f"\n{'='*60}")
        print(f"Schedule Summary: {problem_name}")
        print(f"{'='*60}")
        print(f"Makespan: {result.makespan} seconds ({format_seconds(result.makespan)})")
        print(f"Total Operations: {len(result.operations)}")

        # Group by workshop
        by_workshop: Dict[str, List[ScheduledOperation]] = {}
        for op in result.operations:
            ws = op.process.workshop
            if ws not in by_workshop:
                by_workshop[ws] = []
            by_workshop[ws].append(op)

        for ws in sorted(by_workshop.keys()):
            ops = by_workshop[ws]
            print(f"\nWorkshop {ws}: {len(ops)} operations")
            for op in sorted(ops, key=lambda x: x.start_time):
                print(f"  {op.process.expanded_id()}: "
                      f"{op.equipment.equipment_id} "
                      f"{format_seconds(op.start_time)} - {format_seconds(op.end_time)}")

        if result.total_cost > 0:
            print(f"\nTotal Purchase Cost: {result.total_cost} yuan")

        if result.purchased_equipment:
            print("Purchased Equipment:")
            for eq in result.purchased_equipment:
                print(f"  {eq.equipment_id} ({eq.equipment_type.value})")