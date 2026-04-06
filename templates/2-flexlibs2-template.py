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

def Main(project, report, modify):
    """
    Standard FLExTools entry point.

    This function is called by FLExTools with three parameters:
    - project: FLExProject instance connected to the FieldWorks database
    - report: Report object for logging output (visible in FLExTools UI)
    - modify: Boolean flag - True if modifications are enabled, False for read-only

    Args:
        project (FLExProject): FieldWorks database connection
        report (FTReport): Report object for output
        modify (bool): Whether write operations are enabled

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

                # Process each sense
                for sense in senses:
                    gloss = project.LexSense.GetGloss(sense)
                    definition = project.LexSense.GetDefinition(sense)

                    if gloss:
                        report.Info(f"      - {gloss}")

                    # Example: Modify (only if modify=True)
                    if modify:
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
   if modify:
       project.LexEntry.SetLexemeForm(entry, "new_form")
   else:
       report.Info("(Would modify, but modify=False)")

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
"""
