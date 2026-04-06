"""
FLExTools Module Template

PURPOSE:
    This is a template for writing FLExTools modules that use flexlibs2.
    Replace [Placeholders] with your actual implementation.

CRITICAL REQUIREMENT:
    The flexlibs2 imports below are MANDATORY.
    FLExTools loads stable flexlibs by default. Without explicit flexlibs2 imports,
    your code will silently use the wrong (stable) version, causing subtle bugs.

REQUIRES:
    - FlexLibs2 version 2.0+
    - FieldWorks version [X.Y.Z]+
    - Python 3.7+ (IronPython via FLExTools)

AUTHOR:
    [Your Name / Claude Code]

DATE:
    [Date Created]
"""

# ============================================================================
# CRITICAL: Explicitly import from flexlibs2 (not flexlibs)
# ============================================================================
# This prevents FLExTools's default flexlibs (stable version) from being used
from flexlibs2 import (
    FLExProject,
    LexEntryOperations,
    LexSenseOperations,
    ReversalOperations,
    LexReferenceOperations,
    WritingSystemOperations,
    # Add other operations as needed based on your implementation
)


# ============================================================================
# IMPLEMENTATION
# ============================================================================

def Main(project, report, modifyAllowed):
    """
    Standard FLExTools entry point.

    This function is called by FLExTools with three parameters:
    - project: FLExProject instance connected to the FieldWorks database
    - report: Report object for logging output (visible in FLExTools UI)
    - modify: Boolean flag - True if modifications are enabled, False for read-only

    Args:
        project (FLExProject): FieldWorks database connection
        report (FTReport): Report object for output
        modifyAllowed (bool): Whether write operations are enabled (guard all writes with this)

    Returns:
        None (output via report parameter)
    """
    try:
        # ================================================================
        # Your implementation goes here
        # ================================================================

        # Example: Iterate entries
        report.Info("[INFO] Starting module execution...")

        entries = project.LexEntry.GetAll()
        report.Info(f"Found {len(entries)} lexical entries")

        # Example: Process each entry
        for i, entry in enumerate(entries):
            try:
                # Get entry form (headword)
                form = project.LexEntry.GetLexemeForm(entry)

                # Get all senses for this entry
                senses = project.LexSense.GetAllSenses(entry)
                report.Info(f"  [{i+1}] {form} ({len(senses)} senses)")

                # BuildGoToURL creates clickable links in FLExTools output
                # Users can click to jump directly to entry in FieldWorks GUI
                try:
                    entry_url = project.BuildGotoURL(entry)
                    report.Info(f"      Goto entry: {entry_url}")
                except Exception:
                    # BuildGoToURL might not be available, continue anyway
                    pass

                # Process each sense
                for sense in senses:
                    gloss = project.LexSense.GetGloss(sense)
                    definition = project.LexSense.GetDefinition(sense)

                    if gloss:
                        report.Info(f"      - {gloss}")

                    # BuildGoToURL also works for senses
                    try:
                        sense_url = project.BuildGotoURL(sense)
                        report.Info(f"        Goto sense: {sense_url}")
                    except Exception:
                        pass

                    # Example: Modify (only if modifyAllowed=True)
                    if modifyAllowed:
                        # Your modification logic here
                        pass

            except Exception as e:
                report.Error(f"  Error processing entry: {e}")

        report.Info("[INFO] Module execution complete!")

    except Exception as e:
        report.Error(f"[ERROR] Fatal error: {e}")
        import traceback
        report.Error(traceback.format_exc())


# ============================================================================
# HELPER FUNCTIONS (Optional)
# ============================================================================

def process_entry(project, report, entry, modify):
    """
    Helper function to process a single entry.

    Args:
        project: FLExProject instance
        report: Report object
        entry: ILexEntry object to process
        modify: Boolean flag for write operations

    Returns:
        Boolean - True if successful, False if error
    """
    try:
        form = project.LexEntry.GetLexemeForm(entry)
        report.Debug(f"Processing: {form}")
        return True
    except Exception as e:
        report.Error(f"Error processing entry: {e}")
        return False


def report_with_link(project, report, obj, label):
    """
    Report an object with a clickable link to it in FieldWorks.

    In FLExTools, this creates a clickable link that jumps directly
    to the object in the FieldWorks GUI when clicked.

    Args:
        project: FLExProject instance
        report: Report object
        obj: Object to link to (entry, sense, etc.)
        label: Text to display before the link

    Returns:
        Boolean - True if link created, False if error

    Example:
        report_with_link(project, report, entry, "Entry:")
        Output in FLExTools: "Entry: ftp://localhost:5236/link?app=flex..."
        (Users can click this to jump to the entry)
    """
    try:
        url = project.BuildGotoURL(obj)
        report.Info(f"{label} {url}")
        return True
    except Exception as e:
        report.Debug(f"Could not generate link: {e}")
        return False


# ============================================================================
# NOTES
# ============================================================================

"""
FLEXLIBS2 ADVANTAGES:
  - Handles "***" multistring normalization automatically
  - Comprehensive coverage of FieldWorks APIs (~90%)
  - Better error messages
  - Defensive casting for descriptor issues

COMMON PATTERNS:

1. Iterate entries:
   for entry in project.LexEntry.GetAll():
       form = project.LexEntry.GetLexemeForm(entry)

2. Get senses:
   senses = project.LexSense.GetAllSenses(entry)

3. Check for empty fields (flexlibs2 returns "" not "***"):
   gloss = project.LexSense.GetGloss(sense)
   if not gloss:
       report.Info("Gloss is empty")

4. Modify with permission check:
   if modifyAllowed:
       project.LexEntry.SetLexemeForm(entry, "new_form")
   else:
       report.Info("(Would modify, but modifyAllowed=False)")

5. Error handling:
   try:
       result = project.LexEntry.GetAll()
   except Exception as e:
       report.Error(f"Failed: {e}")

DEBUGGING:
  - Use report.Debug() for verbose output (shows in FLExTools if DEBUG enabled)
  - Use report.Info() for normal progress messages
  - Use report.Error() for errors (these are always shown)
  - Wrap everything in try/except and report errors - FLExTools silences raw exceptions

PERFORMANCE:
  - GetAll() can be slow on large lexicons (1000+ entries)
  - Consider filtering or processing in batches
  - Report progress frequently so user knows it's working

READ-ONLY VS WRITE:
  - Check modify flag before writing
  - If modify=False, still do read operations but skip writes
  - This allows users to preview changes without enabling write mode

BUILDGOTOURL - CLICKABLE LINKS:
  project.BuildGotoURL(obj) creates FLExTools-clickable links.
  Users can click links to jump directly to objects in FieldWorks GUI.

  Supported objects:
    - Lexical entries: project.BuildGotoURL(entry)
    - Senses: project.BuildGotoURL(sense)
    - Reversal entries: project.BuildGotoURL(reversal_entry)
    - And most other FLEx objects

  Example usage:
    entry_url = project.BuildGotoURL(entry)
    report.Info(f"Entry: {entry_url}")

  Or use the helper function:
    report_with_link(project, report, entry, "Click to view:")

  Output in FLExTools:
    Click to view: ftp://localhost:5236/link?app=flex&authority=FLEx&id=47f65d6b...
    (Users can click this hyperlink to jump to the entry)

  Dennis's working example:
    for entry in project.LexEntry.GetAll():
        form = project.LexEntry.GetLexemeForm(entry)
        report.Info(f"  {form}")
        try:
            url = project.BuildGotoURL(entry)
            report.Info(f"  Goto: {url}")
        except Exception:
            pass  # BuildGotoURL not available in this environment

  Always wrap in try/except - BuildGoToURL might not be available
  in all environments or versions.
"""
