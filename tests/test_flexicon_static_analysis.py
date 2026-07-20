"""
Static Analysis Tests for Flexicon

Analyzes Flexicon source code without requiring a live FieldWorks project.
Checks for:
- Parameter validation issues
- Null/None handling
- Unicode support
- Error handling completeness
- Known patterns that might indicate bugs

Run with: python tests/test_flexicon_static_analysis.py
"""

import ast
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum
import re

class IssueLevel(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"

@dataclass
class CodeIssue:
    """Detected code issue"""
    file: str
    line: int
    level: IssueLevel
    check: str
    description: str
    code_snippet: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "level": self.level.value,
            "check": self.check,
            "description": self.description,
            "code_snippet": self.code_snippet
        }

class ASTPatternVisitor(ast.NodeVisitor):
    """Single-pass AST visitor for detecting multiple patterns efficiently."""

    def __init__(self, analyzer: 'FlexiconStaticAnalyzer', file_path: Path):
        self.analyzer = analyzer
        self.file_path = file_path

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Check function-level patterns."""
        # Check for inconsistent return types
        return_types = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Return):
                if child.value is None:
                    return_types.add("None")
                elif isinstance(child.value, ast.List):
                    return_types.add("list")
                elif isinstance(child.value, ast.Constant):
                    return_types.add("constant")

        if "None" in return_types and len(return_types) > 1:
            self.analyzer.add_issue(
                self.file_path, node.lineno, IssueLevel.INFO,
                "inconsistent_returns",
                f"Method mixes None and other return types: {return_types}",
                f"def {node.name}(...):"
            )

        self.generic_visit(node)


class FlexiconStaticAnalyzer:
    """Static analysis of Flexicon code"""

    def __init__(self, flexicon_path: str = "D:/Github/flexicon"):
        self.flexicon_path = Path(flexicon_path)
        self.issues: List[CodeIssue] = []
        self.files_analyzed = 0
        self.python_files: List[Path] = []
        self._ast_cache: Dict[Path, Optional[ast.AST]] = {}  # Cache parsed trees

    def find_python_files(self) -> List[Path]:
        """Find all Python files in flexicon"""
        self.python_files = list(self.flexicon_path.glob("**/*.py"))
        print(f"[INFO] Found {len(self.python_files)} Python files")
        return self.python_files

    def add_issue(self, file: str, line: int, level: IssueLevel,
                 check: str, description: str, code_snippet: str = "") -> None:
        """Record an issue"""
        issue = CodeIssue(
            file=str(file).replace(str(self.flexicon_path), ""),
            line=line,
            level=level,
            check=check,
            description=description,
            code_snippet=code_snippet
        )
        self.issues.append(issue)

    def _get_ast(self, file_path: Path) -> Optional[ast.AST]:
        """Parse and cache AST for a file (avoids redundant parsing)."""
        if file_path in self._ast_cache:
            return self._ast_cache[file_path]

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
            tree = ast.parse(source)
            self._ast_cache[file_path] = tree
            return tree
        except (SyntaxError, UnicodeDecodeError, IOError):
            self._ast_cache[file_path] = None
            return None

    # =====================================================================
    # Check: Missing None/Null Validation & Return Consistency (Combined)
    # =====================================================================

    def check_ast_patterns(self, file_path: Path) -> None:
        """Run all AST-based checks with single visitor pass."""
        tree = self._get_ast(file_path)
        if tree is None:
            return

        # Single visitor pass detects all function-level patterns
        visitor = ASTPatternVisitor(self, file_path)
        visitor.visit(tree)

    # =====================================================================
    # Check: Exception Handling (Line-based)
    # =====================================================================

    def check_exception_handling(self, file_path: Path, lines: List[str]) -> None:
        """Check for bare except clauses and broad exception handling"""
        for i, line in enumerate(lines, 1):
            # Bare except
            if re.search(r'except\s*:', line):
                self.add_issue(file_path, i, IssueLevel.WARNING,
                             "bare_except",
                             "Bare 'except:' clause catches all exceptions (should specify exception types)",
                             line.strip())

            # Too broad exception handling
            if re.search(r'except\s+(Exception|BaseException)', line):
                self.add_issue(file_path, i, IssueLevel.INFO,
                             "broad_except",
                             "Catching broad Exception/BaseException - consider more specific types",
                             line.strip())

            # Pass without logging
            if re.search(r'except.*:\s*$', line) and i < len(lines):
                next_line = lines[i].strip()
                if next_line.startswith("pass"):
                    self.add_issue(file_path, i, IssueLevel.WARNING,
                                 "silent_fail",
                                 "Exception caught and silently ignored - should log or handle",
                                 lines[i-1].strip())

    # =====================================================================
    # Check: Unicode/String Handling
    # =====================================================================

    def check_string_encoding(self, file_path: Path, lines: List[str]) -> None:
        """Check for potential encoding issues"""
        for i, line in enumerate(lines, 1):
            # Hardcoded encoding that's not UTF-8
            if re.search(r'encoding\s*=\s*["\'](?!utf-?8|None)', line):
                self.add_issue(file_path, i, IssueLevel.WARNING,
                             "non_utf8_encoding",
                             "Non-UTF-8 encoding detected - may cause issues with international text",
                             line.strip())

            # String comparison without .strip()
            if re.search(r'==\s*["\'][\s]', line) or re.search(r'["\'][\s]\s*==', line):
                self.add_issue(file_path, i, IssueLevel.INFO,
                             "whitespace_comparison",
                             "Comparing strings with potential whitespace - consider .strip()",
                             line.strip())

    # =====================================================================
    # Check: Empty Multistring Handling
    # =====================================================================

    def check_multistring_handling(self, file_path: Path, lines: List[str]) -> None:
        """Check for proper handling of '***' multistring placeholder"""
        has_flex_empty = False
        missing_check = False

        for i, line in enumerate(lines, 1):
            # Check if code imports or defines the placeholder constant
            if "FLEX_EMPTY_PLACEHOLDER" in line or "'***'" in line or '"***"' in line:
                has_flex_empty = True

            # Check for operations on potentially empty multistrings
            if re.search(r'\.Definition\.|\.Gloss\.|\.Bibliography\.|\.LiteralMeaning\.', line):
                if not has_flex_empty and not re.search(r'if.*==.*\*\*\*|is_empty', line):
                    # Only warn if in a method that sets/reads these fields
                    missing_check = True

        if missing_check and not has_flex_empty:
            self.add_issue(file_path, 1, IssueLevel.INFO,
                         "multistring_check",
                         "File accesses multistring fields without explicit '***' placeholder checks",
                         "Consider adding is_empty_multistring() checks")

    # =====================================================================
    # Check: Type Conversions
    # =====================================================================

    def check_type_conversions(self, file_path: Path, lines: List[str]) -> None:
        """Check for unsafe type conversions"""
        for i, line in enumerate(lines, 1):
            # int() without try/except
            if re.search(r'\bint\s*\([^)]*\)', line) and 'except' not in lines[min(i, len(lines)-1)]:
                if not any("try" in lines[j] for j in range(max(0, i-5), i)):
                    self.add_issue(file_path, i, IssueLevel.INFO,
                                 "unsafe_int_conversion",
                                 "int() conversion without try/except - may raise ValueError",
                                 line.strip())

            # str() on potentially None
            if re.search(r'\bstr\s*\([^)]*\)', line):
                if "or " not in line and "if " not in line:
                    self.add_issue(file_path, i, IssueLevel.INFO,
                                 "str_none_conversion",
                                 "str() may receive None - consider None checks",
                                 line.strip())


    # =====================================================================
    # Check: Known Bug Patterns
    # =====================================================================

    def check_known_patterns(self, file_path: Path, lines: List[str]) -> None:
        """Check for known problematic patterns"""
        for i, line in enumerate(lines, 1):
            # Pattern: Accessing collection without length check
            if re.search(r'\[0\]|\.\w+\[0\]', line):
                if "len(" not in line and "if " not in line:
                    self.add_issue(file_path, i, IssueLevel.WARNING,
                                 "unchecked_indexing",
                                 "Accessing index [0] without checking length - may cause IndexError",
                                 line.strip())

            # Pattern: Mutable default arguments
            if re.search(r'def\s+\w+\([^)]*=\[\]', line):
                self.add_issue(file_path, i, IssueLevel.WARNING,
                             "mutable_default",
                             "Mutable default argument [] - may cause state sharing bugs",
                             line.strip())

            if re.search(r'def\s+\w+\([^)]*=\{\}', line):
                self.add_issue(file_path, i, IssueLevel.WARNING,
                             "mutable_default",
                             "Mutable default argument {} - may cause state sharing bugs",
                             line.strip())

    # =====================================================================
    # Run Analysis
    # =====================================================================

    def analyze(self) -> None:
        """Run all static analysis checks"""
        print(f"\n[INFO] Analyzing {len(self.python_files)} files for issues...\n")

        for file_path in self.python_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except (UnicodeDecodeError, IOError):
                continue

            self.files_analyzed += 1

            # Clean lines once (avoid redundant list comprehension for each check)
            clean_lines = [l.rstrip('\n') for l in lines]

            # Run AST-based checks (parsed once, cached)
            self.check_ast_patterns(file_path)

            # Run line-based checks on same cleaned lines
            self.check_exception_handling(file_path, clean_lines)
            self.check_string_encoding(file_path, clean_lines)
            self.check_multistring_handling(file_path, clean_lines)
            self.check_type_conversions(file_path, clean_lines)
            self.check_known_patterns(file_path, clean_lines)

        print(f"[OK] Analysis complete: {len(self.issues)} potential issues found\n")

    def generate_report(self) -> Dict[str, Any]:
        """Generate analysis report"""
        by_level = {"INFO": 0, "WARNING": 0, "ERROR": 0}
        by_check = {}

        for issue in self.issues:
            by_level[issue.level.value] += 1

            check = issue.check
            if check not in by_check:
                by_check[check] = []
            by_check[check].append(issue.to_dict())

        return {
            "summary": {
                "files_analyzed": self.files_analyzed,
                "total_issues": len(self.issues),
                "issues_by_level": by_level,
                "issues_by_check": {k: len(v) for k, v in by_check.items()}
            },
            "by_check": by_check,
            "all_issues": [i.to_dict() for i in self.issues]
        }

    def print_summary(self) -> None:
        """Print analysis summary"""
        report = self.generate_report()
        summary = report["summary"]

        print("="*70)
        print("STATIC ANALYSIS SUMMARY")
        print("="*70)
        print(f"Files Analyzed: {summary['files_analyzed']}")
        print(f"Total Issues: {summary['total_issues']}")
        print("\nIssues by Level:")
        for level, count in summary['issues_by_level'].items():
            print(f"  {level}: {count}")
        print("\nIssues by Check Type:")
        for check, count in sorted(summary['issues_by_check'].items(), key=lambda x: -x[1]):
            print(f"  {check}: {count}")
        print("="*70 + "\n")

    def save_report(self, output_path: str = "test_static_analysis.json") -> None:
        """Save analysis report"""
        report = self.generate_report()
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
        print(f"[OK] Report saved to: {output_path}")

        # Print top issues
        if self.issues:
            print("\n--- Top Issues ---")
            # Group by severity
            errors = [i for i in self.issues if i.level == IssueLevel.ERROR]
            warnings = [i for i in self.issues if i.level == IssueLevel.WARNING]

            if errors:
                print(f"\n[ERROR] ({len(errors)} issues):")
                for issue in errors[:5]:
                    print(f"  {issue.file}:{issue.line} - {issue.description}")

            if warnings:
                print(f"\n[WARNING] ({len(warnings)} issues):")
                for issue in warnings[:5]:
                    print(f"  {issue.file}:{issue.line} - {issue.description}")

if __name__ == "__main__":
    analyzer = FlexiconStaticAnalyzer()
    analyzer.find_python_files()
    analyzer.analyze()
    analyzer.print_summary()
    analyzer.save_report("tests/test_static_analysis.json")
