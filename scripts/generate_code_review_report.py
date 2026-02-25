#!/usr/bin/env python3
"""
代码审查报告生成脚本

生成包含以下内容的代码审查报告:
- mypy类型检查结果
- black代码格式化检查
- isort导入排序检查
- interrogate文档覆盖率检查
- 总体统计和问题汇总
"""

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List


@dataclass
class CodeIssue:
    """代码问题"""

    file: str
    line: int
    severity: str  # critical, high, medium, low
    category: str  # type, format, import, docstring
    message: str
    code: str = ""


@dataclass
class ModuleReviewSummary:
    """模块审查摘要"""

    module: str
    total_issues: int = 0
    critical_issues: int = 0
    high_issues: int = 0
    medium_issues: int = 0
    low_issues: int = 0
    type_coverage: float = 0.0
    doc_coverage: float = 0.0


@dataclass
class CodeReviewReport:
    """代码审查报告"""

    report_id: str
    generated_at: str
    total_modules_reviewed: int = 0
    total_issues_found: int = 0
    overall_type_coverage: float = 0.0
    overall_doc_coverage: float = 0.0
    module_summaries: List[ModuleReviewSummary] = field(default_factory=list)
    critical_issues: List[CodeIssue] = field(default_factory=list)
    issues_by_severity: dict = field(default_factory=dict)

    def to_dict(self):
        """转换为字典"""
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at,
            "total_modules_reviewed": self.total_modules_reviewed,
            "total_issues_found": self.total_issues_found,
            "overall_type_coverage": self.overall_type_coverage,
            "overall_doc_coverage": self.overall_doc_coverage,
            "module_summaries": [
                {
                    "module": m.module,
                    "total_issues": m.total_issues,
                    "critical_issues": m.critical_issues,
                    "high_issues": m.high_issues,
                    "medium_issues": m.medium_issues,
                    "low_issues": m.low_issues,
                    "type_coverage": m.type_coverage,
                    "doc_coverage": m.doc_coverage,
                }
                for m in self.module_summaries
            ],
            "critical_issues": [
                {
                    "file": i.file,
                    "line": i.line,
                    "severity": i.severity,
                    "category": i.category,
                    "message": i.message,
                    "code": i.code,
                }
                for i in self.critical_issues
            ],
            "issues_by_severity": self.issues_by_severity,
        }


def run_command(cmd: List[str], cwd=None) -> tuple[int, str, str]:
    """运行命令并返回退出码、stdout、stderr"""
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=300
    )
    return result.returncode, result.stdout, result.stderr


def parse_mypy_output(output: str) -> List[CodeIssue]:
    """解析mypy输出"""
    issues = []
    for line in output.split("\n"):
        if ": error: " in line or ": warning: " in line:
            parts = line.split(":")
            if len(parts) >= 3:
                file_path = parts[0].strip()
                line_num = int(parts[1].strip()) if parts[1].strip().isdigit() else 0
                message = ":".join(parts[2:]).strip()

                # 确定严重程度
                severity = "medium"
                if "error" in message.lower():
                    severity = "high"
                elif "warning" in message.lower():
                    severity = "low"

                issues.append(
                    CodeIssue(
                        file=file_path,
                        line=line_num,
                        severity=severity,
                        category="type",
                        message=message,
                    )
                )
    return issues


def parse_black_output(output: str) -> List[CodeIssue]:
    """解析black输出"""
    issues = []
    for line in output.split("\n"):
        if "would reformat" in line:
            file_path = line.strip().split()[-1]
            issues.append(
                CodeIssue(
                    file=file_path,
                    line=0,
                    severity="low",
                    category="format",
                    message="File needs reformatting with black",
                )
            )
    return issues


def parse_isort_output(output: str) -> List[CodeIssue]:
    """解析isort输出"""
    issues = []
    for line in output.split("\n"):
        if "ERROR:" in line and "Imports are incorrectly sorted" in line:
            file_path = line.strip().split()[-1]
            issues.append(
                CodeIssue(
                    file=file_path,
                    line=0,
                    severity="low",
                    category="import",
                    message="Imports are incorrectly sorted",
                )
            )
    return issues


def generate_report(
    project_root: Path = Path("/Users/fish/code/FishAsyncTask"),
) -> CodeReviewReport:
    """生成代码审查报告"""

    report_id = f"CR-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}"
    report = CodeReviewReport(
        report_id=report_id, generated_at=datetime.now().isoformat()
    )

    # 运行mypy
    print("Running mypy...")
    returncode, stdout, stderr = run_command(
        ["mypy", "fish_async_task/"], cwd=project_root
    )
    mypy_output = stdout + stderr
    mypy_issues = parse_mypy_output(mypy_output)

    # 运行black
    print("Running black...")
    returncode, stdout, stderr = run_command(
        ["black", "--check", "fish_async_task/"], cwd=project_root
    )
    black_issues = parse_black_output(stdout + stderr)

    # 运行isort
    print("Running isort...")
    returncode, stdout, stderr = run_command(
        ["isort", "--check-only", "fish_async_task/"], cwd=project_root
    )
    isort_issues = parse_isort_output(stdout + stderr)

    # 运行interrogate
    print("Running interrogate...")
    returncode, stdout, stderr = run_command(
        ["interrogate", "fish_async_task/", "--fail-under=80"], cwd=project_root
    )
    # 提取文档覆盖率
    doc_match = [line for line in stdout.split("\n") if "actual:" in line]
    doc_coverage = 0.0
    if doc_match:
        try:
            doc_coverage = float(doc_match[0].split("actual:")[1].split("%")[0].strip())
        except (IndexError, ValueError):
            pass

    # 汇总所有问题
    all_issues = mypy_issues + black_issues + isort_issues

    # 按严重程度分类
    issues_by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for issue in all_issues:
        issues_by_severity[issue.severity] += 1
        if issue.severity == "critical":
            report.critical_issues.append(issue)

    report.issues_by_severity = issues_by_severity
    report.total_issues_found = len(all_issues)
    report.overall_doc_coverage = doc_coverage

    # 按模块分组
    modules = {}
    for issue in all_issues:
        module = issue.file.split("/")[-1]
        if module not in modules:
            modules[module] = ModuleReviewSummary(module=module)
        modules[module].total_issues += 1
        if issue.severity == "critical":
            modules[module].critical_issues += 1
        elif issue.severity == "high":
            modules[module].high_issues += 1
        elif issue.severity == "medium":
            modules[module].medium_issues += 1
        elif issue.severity == "low":
            modules[module].low_issues += 1
        modules[module].doc_coverage = doc_coverage

    report.module_summaries = list(modules.values())
    report.total_modules_reviewed = len(modules)

    return report


def main():
    """主函数"""
    import sys

    project_root = Path.cwd()
    if len(sys.argv) > 1:
        project_root = Path(sys.argv[1])

    print(f"Generating code review report for {project_root}...")
    report = generate_report(project_root)

    # 输出JSON报告
    report_file = project_root / "specs/001-code-review-test-coverage" / "code_review_report.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)

    with open(report_file, "w") as f:
        json.dump(report.to_dict(), f, indent=2)

    print(f"\n{'='*60}")
    print(f"Code Review Report: {report.report_id}")
    print(f"{'='*60}")
    print(f"Total modules reviewed: {report.total_modules_reviewed}")
    print(f"Total issues found: {report.total_issues_found}")
    print(f"Overall doc coverage: {report.overall_doc_coverage:.1f}%")
    print(f"\nIssues by severity:")
    for severity, count in report.issues_by_severity.items():
        print(f"  {severity.capitalize()}: {count}")
    print(f"\nReport saved to: {report_file}")
    print(f"{'='*60}")

    return 0


if __name__ == "__main__":
    exit(main())
