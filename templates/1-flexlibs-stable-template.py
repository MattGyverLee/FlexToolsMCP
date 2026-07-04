"""
FLExTools Module: [Module Name] (FlexLibs Stable v1.x)

PURPOSE:
    [What this module does]

REQUIRES:
    - FlexLibs stable version 1.2.8+
    - FieldWorks version [X.Y.Z]+ (typically 8.x - 9.x)

⚠️  LEGACY VERSION
    This template uses stable flexlibs. For new projects, use flexicon.
    See 2-flexicon-template.py for recommended approach.

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


def Main(project, report, modifyAllowed):
    """
    Standard FLExTools entry point for stable flexlibs.

    Args:
        project (FLExProject): FieldWorks database connection
        report (FTReport): Report object for output
        modifyAllowed (bool): Whether write operations are enabled (guard all writes with this)
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
                # (flexicon has much better coverage)
                report.Info(f"  [{i+1}] {form}")

                # BuildGoToURL creates clickable links in FLExTools output
                # Users can click to jump to entry in FieldWorks GUI
                try:
                    entry_url = project.BuildGotoURL(entry)
                    report.Info(f"      Goto: {entry_url}")
                except Exception as url_error:
                    # BuildGoToURL not available in all versions
                    pass

                # Multistring fields return "***" when empty
                # Must check explicitly
                if modifyAllowed:
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
# HELPER FUNCTIONS
# ============================================================================

def report_with_goto(project, report, obj, label):
    """
    Report an object with a clickable link to it in FieldWorks.

    Args:
        project: FLExProject instance
        report: Report object
        obj: Object to link to (entry, sense, etc.)
        label: Text to display before the link

    Example:
        report_with_goto(project, report, entry, "Lexeme:")
        Output: "Lexeme: ftp://localhost:..."
    """
    try:
        url = project.BuildGotoURL(obj)
        report.Info(f"{label} {url}")
        return True
    except Exception as e:
        report.Debug(f"Could not generate link: {e}")
        return False


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
  If your system supports FieldWorks 9.0+, use flexicon instead:
    - 90% API coverage (vs ~40 functions)
    - Automatic "***" normalization
    - Better error messages
    - More operations on every object

MIGRATION PATH:
  1. Check if FieldWorks version is 9.0+
  2. Check if Flexicon is available
  3. Use 2-flexicon-template.py instead
  4. Minimal code changes needed

BUILDGOTOURL - CLICKABLE LINKS:
  project.BuildGotoURL(obj) creates FLExTools-clickable links.
  Users can click links to jump directly to objects in FieldWorks GUI.

  Supported objects:
    - Lexical entries: project.BuildGotoURL(entry)
    - Senses: project.BuildGotoURL(sense)
    - Reversal entries: project.BuildGotoURL(reversal_entry)
    - And most other FLEx objects

  Example output in FLExTools:
    Found entry: ftp://localhost:5236/link?app=flex&authority=FLEx&id=47f65d6b-d92a-4149-a9c9-3ec5f6e1e2ab
    (users can click this link)

  Wrapped in try/except because BuildGotoURL may not be available
  in all versions or environments.

WHY NOT FLEXICON?
  This template is only for systems where:
    - FieldWorks < 9.0 (old systems)
    - Flexicon not available
    - System is locked down
    - Other constraints prevent upgrade
"""
