"""
FLExTools Module: [Module Name] (FlexLibs Stable v1.x)

PURPOSE:
    [What this module does]

REQUIRES:
    - FlexLibs stable version 1.2.8+
    - FieldWorks version [X.Y.Z]+ (typically 8.x - 9.x)

⚠️  LEGACY VERSION
    This template uses stable flexlibs. For new projects, use flexlibs2.
    See 2-flexlibs2-template.py for recommended approach.

AUTHOR:
    [Your Name / Claude Code]

DATE:
    [Date Created]
"""

# ============================================================================
# FLEXLIBS STABLE IMPORTS (Legacy)
# ============================================================================
# Limited API - only ~40 core functions available
from flexlibs import FLExProject, FP_RuntimeError


def Main(project, report, modify):
    """
    Standard FLExTools entry point for stable flexlibs.

    Args:
        project (FLExProject): FieldWorks database connection
        report (FTReport): Report object for output
        modify (bool): Whether write operations are enabled
    """
    try:
        # ================================================================
        # Your implementation goes here
        # ================================================================

        report.Info("[INFO] Starting legacy flexlibs module...")

        # Note: Limited API - only basic operations available
        entries = project.LexAllEntries()  # Returns all entries
        report.Info(f"Found {len(entries)} entries")

        for i, entry in enumerate(entries):
            try:
                # Get entry form (headword)
                form = project.LexiconGetEntryForm(entry)

                # Limited sense operations available
                # (flexlibs2 has much better coverage)
                report.Info(f"  [{i+1}] {form}")

                # Multistring fields return "***" when empty
                # Must check explicitly
                if modify:
                    # Your modification logic here
                    pass

            except FP_RuntimeError as e:
                report.Error(f"  Error processing entry: {e}")

        report.Info("[INFO] Module execution complete!")

    except Exception as e:
        report.Error(f"[ERROR] Fatal error: {e}")
        import traceback
        report.Error(traceback.format_exc())


# ============================================================================
# NOTES ON STABLE FLEXLIBS
# ============================================================================

"""
LIMITED CAPABILITIES:
  ~40 core functions:
    - LexAllEntries()
    - LexiconGetEntryForm()
    - LexiconGetFieldText()
    - And others...

  NOT available:
    - GetAllSenses() / per-sense operations
    - GetAllReversals()
    - Complex transformations
    - Type safety

MULTISTRING HANDLING:
  Stable flexlibs returns "***" for empty multilingual fields.
  You must check explicitly:

    def get_form_safe(project, entry):
        form = project.LexiconGetEntryForm(entry)
        return "" if form == "***" else form

CONSIDER UPGRADING:
  If your system supports FieldWorks 9.0+, use flexlibs2 instead:
    - 90% API coverage (vs ~40 functions)
    - Automatic "***" normalization
    - Better error messages
    - More operations on every object

MIGRATION PATH:
  1. Check if FieldWorks version is 9.0+
  2. Check if FlexLibs2 is available
  3. Use 2-flexlibs2-template.py instead
  4. Minimal code changes needed

WHY NOT FLEXLIBS2?
  This template is only for systems where:
    - FieldWorks < 9.0 (old systems)
    - FlexLibs2 not available
    - System is locked down
    - Other constraints prevent upgrade
"""
