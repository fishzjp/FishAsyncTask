#!/usr/bin/env python3
"""
测试覆盖率报告生成脚本

解析coverage.xml或pytest输出,生成详细的测试覆盖率报告
"""

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class ModuleCoverage:
    """模块覆盖率"""

    module: str
    lines_covered: int = 0
    lines_total: int = 0
    line_coverage: float = 0.0
    branches_covered: int = 0
    branches_total: int = 0
    branch_coverage: float = 0.0
    missing_lines: List[int] = field(default_factory=list)


@dataclass
class TestCoverageReport:
    """测试覆盖率报告"""

    report_id: str
    generated_at: str
    total_modules: int = 0
    overall_line_coverage: float = 0.0
    overall_branch_coverage: float = 0.0
    module_coverages: Dict[str, ModuleCoverage] = field(default_factory=dict)
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0

    def to_dict(self):
        """转换为字典"""
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at,
            "total_modules": self.total_modules,
            "overall_line_coverage": self.overall_line_coverage,
            "overall_branch_coverage": self.overall_branch_coverage,
            "module_coverages": {
                name: {
                    "module": cov.module,
                    "lines_covered": cov.lines_covered,
                    "lines_total": cov.lines_total,
                    "line_coverage": cov.line_coverage,
                    "branches_covered": cov.branches_covered,
                    "branches_total": cov.branches_total,
                    "branch_coverage": cov.branch_coverage,
                    "missing_lines": cov.missing_lines,
                }
                for name, cov in self.module_coverages.items()
            },
            "tests_run": self.tests_run,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "tests_skipped": self.tests_skipped,
        }


def parse_coverage_xml(xml_path: Path) -> TestCoverageReport:
    """解析coverage.xml文件"""

    tree = ET.parse(xml_path)
    root = tree.getroot()

    report_id = f"TC-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}"
    coverage_report = TestCoverageReport(
        report_id=report_id, generated_at=datetime.now().isoformat()
    )

    # 解析包/模块
    for package in root.findall(".//packages/package"):
        for module_elem in package.findall("classes/class"):
            filename = module_elem.get("filename", "")
            module_name = filename.replace("/", ".").replace(".py", "")

            # 获取行覆盖率
            lines_elem = module_elem.find("lines")
            lines_total = 0
            lines_covered = 0
            missing_lines = []

            if lines_elem is not None:
                for line in lines_elem.findall("line"):
                    lines_total += 1
                    if line.get("hits", "0") != "0":
                        lines_covered += 1
                    else:
                        missing_lines.append(int(line.get("number", "0")))

            # 计算覆盖率
            line_coverage = (
                (lines_covered / lines_total * 100) if lines_total > 0 else 0.0
            )

            module_cov = ModuleCoverage(
                module=module_name,
                lines_covered=lines_covered,
                lines_total=lines_total,
                line_coverage=line_coverage,
                missing_lines=missing_lines,
            )

            coverage_report.module_coverages[module_name] = module_cov

    # 计算总体覆盖率
    coverage_report.total_modules = len(coverage_report.module_coverages)
    if coverage_report.total_modules > 0:
        total_lines = sum(m.lines_total for m in coverage_report.module_coverages.values())
        total_covered = sum(
            m.lines_covered for m in coverage_report.module_coverages.values()
        )
        coverage_report.overall_line_coverage = (
            (total_covered / total_lines * 100) if total_lines > 0 else 0.0
        )

    return coverage_report


def parse_pytest_output(output_path: Path) -> Dict[str, int]:
    """解析pytest输出文件,提取测试统计"""

    stats = {"run": 0, "passed": 0, "failed": 0, "skipped": 0}

    if not output_path.exists():
        return stats

    content = output_path.read_text()

    # 查找测试统计行
    for line in content.split("\n"):
        if "passed" in line.lower():
            # 解析类似 "123 passed, 2 failed, 5 skipped in 10.5s" 的行
            parts = line.lower().split()
            for i, part in enumerate(parts):
                if "passed" in part and i > 0:
                    try:
                        stats["passed"] = int(parts[i - 1])
                    except (ValueError, IndexError):
                        pass
                elif "failed" in part and i > 0:
                    try:
                        stats["failed"] = int(parts[i - 1])
                    except (ValueError, IndexError):
                        pass
                elif "skipped" in part and i > 0:
                    try:
                        stats["skipped"] = int(parts[i - 1])
                    except (ValueError, IndexError):
                        pass

    stats["run"] = stats["passed"] + stats["failed"] + stats["skipped"]
    return stats


def generate_report(
    project_root: Path = Path("/Users/fish/code/FishAsyncTask"),
) -> TestCoverageReport:
    """生成测试覆盖率报告"""

    # 查找coverage.xml
    coverage_xml = project_root / "coverage.xml"
    pytest_output = project_root / "tmp" / "coverage_baseline.txt"

    report_id = f"TC-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}"

    if coverage_xml.exists():
        coverage_report = parse_coverage_xml(coverage_xml)
        coverage_report.report_id = report_id
    else:
        coverage_report = TestCoverageReport(
            report_id=report_id, generated_at=datetime.now().isoformat()
        )

    # 解析pytest统计
    test_stats = parse_pytest_output(pytest_output)
    coverage_report.tests_run = test_stats["run"]
    coverage_report.tests_passed = test_stats["passed"]
    coverage_report.tests_failed = test_stats["failed"]
    coverage_report.tests_skipped = test_stats["skipped"]

    return coverage_report


def main():
    """主函数"""
    import sys

    project_root = Path.cwd()
    if len(sys.argv) > 1:
        project_root = Path(sys.argv[1])

    print(f"Generating test coverage report for {project_root}...")
    report = generate_report(project_root)

    # 输出JSON报告
    report_file = (
        project_root / "specs/001-code-review-test-coverage" / "test_coverage_report.json"
    )
    report_file.parent.mkdir(parents=True, exist_ok=True)

    with open(report_file, "w") as f:
        json.dump(report.to_dict(), f, indent=2)

    print(f"\n{'='*60}")
    print(f"Test Coverage Report: {report.report_id}")
    print(f"{'='*60}")
    print(f"Total modules: {report.total_modules}")
    print(f"Overall line coverage: {report.overall_line_coverage:.1f}%")
    print(f"Overall branch coverage: {report.overall_branch_coverage:.1f}%")
    print(f"\nTests:")
    print(f"  Run: {report.tests_run}")
    print(f"  Passed: {report.tests_passed}")
    print(f"  Failed: {report.tests_failed}")
    print(f"  Skipped: {report.tests_skipped}")
    print(f"\nModule coverages:")
    for module, cov in sorted(report.module_coverages.items()):
        print(
            f"  {module}: {cov.line_coverage:.1f}% ({cov.lines_covered}/{cov.lines_total} lines)"
        )
    print(f"\nReport saved to: {report_file}")
    print(f"{'='*60}")

    return 0


if __name__ == "__main__":
    exit(main())
