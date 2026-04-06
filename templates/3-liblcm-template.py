"""
FLExTools Module: [Module Name] (LibLCM Direct C#)

PURPOSE:
    [What this module does - ideally something that requires edge case access]

REQUIRES:
    - FlexLibs2 2.0+ (for casting utilities)
    - FieldWorks 9.0+
    - Python/IronPython with pythonnet support

⚠️  ADVANCED: POWER USERS ONLY
    This template uses direct LibLCM C# access. Complex code, hard to maintain.
    Use only for edge cases not covered by flexlibs2.
    See 2-flexlibs2-template.py for recommended approach first.

AUTHOR:
    [Your Name / Claude Code]

DATE:
    [Date Created]
"""

# ============================================================================
# LIBLCM IMPORTS (Direct C# Access)
# ============================================================================

# pythonnet for C# interop
import clr

# FlexLibs2 casting utilities
from flexlibs2.code.lcm_casting import cast_to_concrete
from flexlibs2.code.lcm_casting import (
    ILexEntry,
    ILexSense,
    ILexEntryRef,
    IReversalIndexEntry,
    # Add other interfaces as needed
)


def Main(project, report, modify):
    """
    Standard FLExTools entry point with LibLCM direct access.

    Args:
        project (FLExProject): FieldWorks database connection
        report (FTReport): Report object for output
        modify (bool): Whether write operations are enabled

    Note:
        This template accesses the underlying C# object model directly.
        Requires understanding of FieldWorks/LibLCM data structures.
    """
    try:
        # ================================================================
        # Your implementation goes here
        # ================================================================

        report.Info("[INFO] Starting LibLCM-based module...")

        # Access the C# service locator for raw objects
        try:
            service_locator = project.ServiceLocator
            lex_db = service_locator.GetInstance("ILexdbAccess")
        except Exception as e:
            report.Error(f"Failed to access ServiceLocator: {e}")
            return

        # Iterate all LexEntry objects directly
        try:
            # Get raw C# collection
            entry_collection = lex_db.AllInstances("LexEntry")
            entry_count = entry_collection.Count

            report.Info(f"Found {entry_count} entries (raw C#)")

            for i, entry_hvo in enumerate(entry_collection):
                try:
                    # Cast to concrete LexEntry interface
                    entry = cast_to_concrete(entry_hvo, ILexEntry)

                    # Access C# properties directly
                    form_ws = entry.LexemeForm
                    if form_ws is None:
                        form = ""
                    else:
                        # MultiString access (need to check for "***")
                        form_text = form_ws.VernacularForm.Text
                        form = "" if form_text == "***" else form_text

                    report.Info(f"  [{i+1}] {form}")

                    # Access senses through C# object reference
                    senses_collection = entry.SensesOS
                    sense_count = senses_collection.Count if senses_collection else 0

                    # Process senses
                    for j, sense_hvo in enumerate(senses_collection or []):
                        sense = cast_to_concrete(sense_hvo, ILexSense)

                        # Access C# gloss property
                        gloss_ws = sense.Gloss
                        if gloss_ws:
                            gloss_text = gloss_ws.AnalysisDefaultWritingSystem.Text
                            gloss = "" if gloss_text == "***" else gloss_text
                            report.Info(f"      [{j+1}] {gloss}")

                except Exception as sense_error:
                    report.Error(f"  Error processing sense: {sense_error}")

        except Exception as e:
            report.Error(f"Error accessing entries: {e}")
            import traceback
            report.Error(traceback.format_exc())

        report.Info("[INFO] Module execution complete!")

    except Exception as e:
        report.Error(f"[ERROR] Fatal error: {e}")
        import traceback
        report.Error(traceback.format_exc())


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_multistring_safe(multistring, writing_system_id=None):
    """
    Safely get text from a LibLCM MultiString.

    Args:
        multistring: IMultiString object from C#
        writing_system_id: Optional specific writing system ID

    Returns:
        str: Text content (empty string if "***" or None)
    """
    if multistring is None:
        return ""

    try:
        if writing_system_id:
            text = multistring.get_String(writing_system_id).Text
        else:
            text = multistring.BestAnalysisAlternative.Text

        return "" if text == "***" else text
    except:
        return ""


def cast_to_interface(obj, interface_type):
    """
    Helper to cast C# object to concrete interface.

    Args:
        obj: Raw C# object
        interface_type: Interface class from flexlibs2.code.lcm_casting

    Returns:
        Casted object or None if cast fails
    """
    try:
        return cast_to_concrete(obj, interface_type)
    except Exception as e:
        return None


# ============================================================================
# NOTES ON LIBLCM DIRECT ACCESS
# ============================================================================

"""
WHAT IS LIBLCM?
  LibLCM is the C# data model underlying FieldWorks.
  Direct access = 100% API coverage, but complex code.

WHEN TO USE:
  - Edge cases not covered by flexlibs2
  - Performance-critical inner loops
  - Complex data structure manipulation
  - Custom type handling

WHEN NOT TO USE:
  - Simple read/write operations (use flexlibs2)
  - Team not familiar with C#
  - Maintenance burden is concern
  - Code readability matters more than power

KEY DIFFERENCES FROM FLEXLIBS2:
  1. Raw C# access (no Python-friendly wrappers)
  2. Multistring fields return "***" (must check)
  3. Collections are C# IEnumerable (not Python lists)
  4. Type casting required for safe access
  5. No error message improvements
  6. Direct property access (no methods)

COMMON PATTERNS:

1. Access ServiceLocator (entry point to C#):
   service_locator = project.ServiceLocator
   lex_db = service_locator.GetInstance("ILexdbAccess")

2. Iterate collections:
   for item in collection:
       casted = cast_to_concrete(item, ILexEntry)

3. Handle MultiString fields:
   if field.Text == "***":
       value = ""
   else:
       value = field.Text

4. Navigate C# properties:
   entry.SensesOS  # C# property access (not method)
   sense.Gloss  # Direct property

5. Write with permission check:
   if modify:
       entry.LexemeForm = new_value  # Direct C# assignment

PYTHONNET INTEGRATION:
  When you need low-level C# interop:
    import clr
    clr.AddReference("SIL.FieldWorks.Common.COMInterfaces")

  But usually project.ServiceLocator gives you what you need.

PERFORMANCE:
  Direct C# access is fast but iterating large collections
  can be slow. Consider:
    - Batch operations
    - Filtering at C# level if possible
    - Caching results

DEBUGGING:
  Hard to debug C# objects from Python. Use:
    report.Info(f"Object type: {type(obj)}")
    report.Info(f"Object properties: {dir(obj)}")
    report.Info(f"Collection count: {collection.Count}")

WHEN FLEXLIBS2 IS NOT ENOUGH:
  Compare before choosing LibLCM:

  # FlexLibs2 (easier)
  form = project.LexEntry.GetLexemeForm(entry)  # Returns ""

  # LibLCM (harder)
  entry_obj = cast_to_concrete(entry, ILexEntry)
  form_text = entry_obj.LexemeForm.VernacularForm.Text
  if form_text == "***":
      form = ""

  Unless you NEED that extra power, use flexlibs2.
"""
