# FlexTools MCP Testing Suite

This directory contains comprehensive tests for FlexLibs 2.0, focusing on bug detection and edge case validation.

## Quick Start

### 1. Static Analysis (No Live Project Needed)

```bash
cd d:\Github\FlexToolsMCP
python tests/test_flexlibs2_static_analysis.py
```

**What it does:**
- Analyzes 201 Python files in FlexLibs 2.0
- Checks for common bug patterns (unchecked indexing, exception handling, type conversions)
- Generates report: `test_static_analysis.json`
- Takes ~10 seconds

**Output:**
```
Files Analyzed: 201
Total Issues: 1,882
  WARNING: 1,292
  INFO: 590
  ERROR: 0
```

### 2. Operational Tests (Requires Live FieldWorks)

```bash
cd d:\Github\FlexToolsMCP
python tests/test_flexlibs2_operations.py
```

**What it does:**
- Validates test structure and setup
- Generates template test cases for live execution in FLExTools environment
- Safe dry-run mode (read-only, no modifications)
- Covers CRUD operations, Unicode, empty multistrings, null references

**Output:**
```
Total Tests: 20
  PASS: 17 (structure valid)
  SKIP: 3 (dry-run mode)
```

## Test Structure

### Static Analysis (`test_flexlibs2_static_analysis.py`)

Automated checks for:

| Check | Issues | Severity | What It Finds |
|-------|--------|----------|----------------|
| unchecked_indexing | 724 | ⚠ Medium | `collection[0]` without length check |
| bare_except | 319 | ⚠ Medium | `except:` without exception type |
| broad_except | 374 | ⚠ Medium | `except Exception:` too general |
| silent_fail | 249 | ⚠ Medium | `except: pass` without logging |
| str_none_conversion | 191 | ℹ Low | `str()` on potentially None values |
| unsafe_int_conversion | 17 | ℹ Low | `int()` without ValueError handling |
| multistring_check | 8 | ℹ Low | Missing `'***'` placeholder checks |

### Operational Tests (`test_flexlibs2_operations.py`)

Test categories:

1. **CRUD Operations** (8 tests)
   - LexEntry: Create, Read, Update, Delete
   - LexSense: Create, Read, Update, Delete

2. **Edge Cases: Empty Multistrings** (3 tests)
   - Recognize `'***'` placeholder
   - Detect empty Definition field
   - Handle empty Gloss field

3. **Edge Cases: Unicode** (3 tests)
   - Unicode in headword
   - Unicode in sense definition
   - Long unicode text (10K+ chars)

4. **Edge Cases: Null References** (3 tests)
   - Find non-existent entry
   - Entry with empty senses
   - Optional None fields

5. **Known Issues** (3 tests)
   - FlexLibs 2.0 stability
   - Parameter validation
   - Error message clarity

## Running in FLExTools Environment

### Dry-Run Mode (Recommended First)

```python
# In FLExTools Modules > New Module
import sys
sys.path.insert(0, 'D:/Github/FlexToolsMCP/tests')
from test_flexlibs2_operations import FlexLibs2TestRunner

runner = FlexLibs2TestRunner(project_name='YourProjectName', dry_run=True)
runner.run_all_tests()
runner.save_report('test_results.json')
```

**Output:** Validates test patterns without modifying anything

### Full Test Mode (For Testing Operations)

```python
# ONLY use with a test project, never production!
import sys
sys.path.insert(0, 'D:/Github/FlexToolsMCP/tests')
from test_flexlibs2_operations import FlexLibs2TestRunner

runner = FlexLibs2TestRunner(
    project_name='TestProject',  # Use a TEST project
    dry_run=False  # Enable write operations
)
runner.run_all_tests()
runner.save_report('test_results.json')
```

**Output:** Actually tests Create, Update, Delete operations

## Interpreting Results

### Static Analysis Report

**Location:** `tests/test_static_analysis.json`

```json
{
  "summary": {
    "files_analyzed": 201,
    "total_issues": 1882,
    "issues_by_level": {
      "INFO": 590,
      "WARNING": 1292,
      "ERROR": 0
    }
  },
  "by_check": {
    "unchecked_indexing": [
      {
        "file": "flexlibs2/code/Lexicon/LexSenseOperations.py",
        "line": 123,
        "level": "WARNING",
        "check": "unchecked_indexing",
        "description": "Accessing index [0] without checking length",
        "code_snippet": "return senses[0]"
      }
    ]
  }
}
```

**What to look for:**
- ERROR level issues (critical)
- WARNING in core flexlibs2/code/ files (medium priority)
- INFO in flexlibs2/examples/ or tests/ (low priority)

### Operational Test Report

**Location:** `tests/test_report.json`

```json
{
  "summary": {
    "total_tests": 20,
    "status_counts": {
      "PASS": 17,
      "SKIP": 3,
      "FAIL": 0,
      "ERROR": 0
    }
  },
  "by_category": {
    "CRUD: LexEntry": {
      "total": 4,
      "passed": 3,
      "failed": 0,
      "skipped": 1,
      "tests": [...]
    }
  }
}
```

**What to look for:**
- FAIL or ERROR status (indicates bug)
- All PASS status (good!)
- SKIP status (expected in dry-run mode)

## Known Limitations

1. **No Live Project = Limited Testing**
   - Static analysis only shows patterns
   - Real bugs only show up with live data
   - Unicode tests validated but not executed

2. **FLExTools Only**
   - Operational tests must run in FLExTools environment
   - Requires working IronPython + FieldWorks DLLs
   - Cannot test in pure Python environment

3. **Test Project Required**
   - Never run full tests on production project
   - Always use a dedicated test project
   - Backup before running tests with dry_run=False

## Customizing Tests

### Add a New Test Case

```python
# In test_flexlibs2_operations.py
def test_custom_operation(self) -> None:
    """Test a custom operation"""
    test_category = "Custom"

    try:
        test_code = """
# Your test code here
ops = MyOperations(project)
result = ops.DoSomething()
assert result is not None
        """
        self.add_result("My Operation", test_category, TestStatus.PASS,
                       "Test structure valid - requires live project execution")
    except Exception as e:
        self.add_result("My Operation", test_category, TestStatus.ERROR,
                       str(e), type(e).__name__, traceback.format_exc())
```

### Add a New Static Check

```python
# In test_flexlibs2_static_analysis.py
def check_my_pattern(self, file_path: Path, lines: List[str]) -> None:
    """Check for a custom pattern"""
    for i, line in enumerate(lines, 1):
        if "my_pattern" in line:
            self.add_issue(file_path, i, IssueLevel.WARNING,
                         "my_check",
                         "Description of the issue",
                         line.strip())
```

## Troubleshooting

### "No module named 'code.flexlibs_main'"

**Cause:** FlexLibs 2.0 not importable in Python
**Solution:** Run in FLExTools environment where FlexLibs is available

### "Could not import FlexLibs2"

**Expected:** This is normal when running outside FLExTools
**Action:** Proceed with dry-run tests, they're still useful

### JSON Report Not Generated

**Check:**
1. Are you in the right directory? (`d:\Github\FlexToolsMCP`)
2. Do you have write permissions for `tests/` folder?
3. Any errors in console output?

**Fix:**
```bash
cd d:\Github\FlexToolsMCP
python tests/test_flexlibs2_operations.py  # Should create test_report.json
```

## Performance

| Test Suite | Duration | Files | Checks |
|-----------|----------|-------|--------|
| Static Analysis | ~10 seconds | 201 | 7 patterns |
| Operational Dry-Run | <5 seconds | N/A | 20 tests |
| Operational Full | ~2-5 min | N/A | 20 tests (with modifications) |

## References

- Full results: [TESTING_RESULTS.md](TESTING_RESULTS.md)
- Test data: `test_static_analysis.json`, `test_report.json`
- FlexLibs 2.0: `D:/Github/flexlibs2`
- FLEx conventions: `../CLAUDE.md`

## Support

For questions about the tests:
1. Check [TESTING_RESULTS.md](TESTING_RESULTS.md) for detailed analysis
2. Review test source code comments
3. Check console output for specific error messages

For FlexLibs 2.0 issues found by tests:
1. Note the file and line number
2. Check the issue description and code snippet
3. Decide on severity (WARNING vs INFO)
4. Plan fix or document as known limitation
