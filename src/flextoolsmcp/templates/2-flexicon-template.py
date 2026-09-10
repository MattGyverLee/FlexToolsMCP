"""
FLExTools Module Template

PURPOSE:
    This is a template for writing FLExTools modules that use flexicon.
    Replace [Placeholders] with your actual implementation.

CRITICAL REQUIREMENT:
    The flexicon imports below are MANDATORY.
    FLExTools loads stable flexlibs by default. Without explicit flexicon imports,
    your code will silently use the wrong (stable) version, causing subtle bugs.

REQUIRES:
    - flexicon (pip install pyflexicon), new enough to have
      FLExProject.FromOpenProject(). The pre-flight below checks for the
      capability itself rather than for a version number, and reports what to
      do if it is absent.
    - FieldWorks version [X.Y.Z]+
    - Python 3.7+ (IronPython via FLExTools)

AUTHOR:
    [Your Name / Claude Code]

DATE:
    [Date Created]
"""

# ============================================================================
# CRITICAL: Explicitly import from flexicon (not flexlibs)
# ============================================================================
# This prevents FLExTools's default flexlibs (stable version) from being used
#
# The import is guarded so that a missing pyflexicon becomes a readable message
# from _flexicon_preflight() below, instead of an ImportError traceback thrown
# before Main() is ever reached. FlexTools shows that traceback with no remedy
# and no hint that the module itself is fine.
#
# The two imports are guarded SEPARATELY on purpose. `except ImportError`
# cannot tell "no such package" from "no such name in the package", so a single
# try block around both made a wrong operations name below report as "flexicon
# is not installed" -- sending the user to `pip install` for a package they
# already have, while insisting the module needed no editing when the import
# list was the only thing that did.
_FLEXICON_IMPORT_ERROR = None
_FLEXICON_SYMBOL_ERROR = None

try:
    import flexicon as _flexicon
except ImportError as _import_error:
    _flexicon = None
    _FLEXICON_IMPORT_ERROR = str(_import_error)

FLExProject = None
if _flexicon is not None:
    try:
        from flexicon import (
            FLExProject,
            LexEntryOperations,
            LexSenseOperations,
            LexReferenceOperations,
            WritingSystemOperations,
            # Add other operations as needed based on your implementation.
            # Import only names flexicon actually exports -- a wrong name here is
            # an ImportError that stops the module before Main() runs (the
            # pre-flight below will tell you which name, and that this list is
            # what to fix). Reversal work, for example, has no top-level
            # "ReversalOperations": reach it through the accessors
            # project.ReversalIndexes / project.ReversalEntries instead.
        )
    except ImportError as _symbol_error:
        _FLEXICON_SYMBOL_ERROR = str(_symbol_error)


# ============================================================================
# ENVIRONMENT PRE-FLIGHT
# ============================================================================
# Two things can be wrong with the Python environment your FlexTools install
# uses, and neither one reads as an environment problem on its own:
#
#   1. pyflexicon is not installed at all -> ImportError at load time.
#   2. pyflexicon is installed but predates FLExProject.FromOpenProject()
#      -> the module imports cleanly and then dies on the first line of Main()
#         with "type object 'FLExProject' has no attribute 'FromOpenProject'".
#
# A third case is the module's fault rather than the environment's: a name in
# the import list above that flexicon does not export. It gets its own message,
# because the remedy is the opposite one -- edit this file, do not touch the
# environment.
#
# In both cases the module is correct and the environment is not, which is
# exactly what a user cannot tell from the raw traceback. The pre-flight says so
# and names the fix.
#
# There is also a third, milder case: a flexicon that HAS the bridge but is
# older than the one this module was written against. That is not an error and
# must never stop the module -- it is a note worth having in a bug report.

# The flexicon version present when this module was generated. Stamped by
# flextools_get_module_template(); stays "unknown" if the template file is
# copied by hand, in which case the version note below is skipped entirely
# rather than guessed at.
_TESTED_AGAINST = "unknown"


def _flexicon_installed_version():
    """
    Best-effort flexicon version string, for the diagnostic message only.

    Never raises, and never gates anything -- see _flexicon_preflight() for why
    the gate is a capability probe rather than a version floor. Returns the
    string "unknown" when it cannot tell.
    """
    try:
        found = getattr(_flexicon, "version", None)
        if found:
            return str(found)
    except Exception:
        pass

    try:
        import importlib.metadata as _metadata

        found = _metadata.version("pyflexicon")
        if found:
            return str(found)
    except Exception:
        pass

    return "unknown"


def _version_parts(text):
    """
    Turn "4.10.2" into (4, 10, 2) for ordering. Never raises.

    Returns None when the string is not a plain dotted number -- "unknown", a
    dev suffix, a git hash. None means "do not compare", which is the safe
    answer: a comparison we cannot trust must produce no note at all rather
    than a wrong one.
    """
    try:
        pieces = str(text).strip().split(".")
        if not pieces:
            return None
        out = []
        for piece in pieces:
            if not piece.isdigit():
                return None
            out.append(int(piece))
        return tuple(out)
    except Exception:
        return None


def _flexicon_is_behind(found, tested):
    """
    True only when both strings parse AND found is genuinely the older one.

    Never raises, and answers False whenever there is any doubt. This informs a
    WARNING only -- it must never decide whether the module runs. See
    _flexicon_preflight() for why the gate is hasattr and nothing else.
    """
    left = _version_parts(found)
    right = _version_parts(tested)
    if left is None or right is None:
        return False
    return left < right


def _report_preflight_error(report, lines):
    """Emit the diagnostic, tolerating a report object that itself misbehaves."""
    for line in lines:
        try:
            report.Error(line)
        except Exception:
            pass


def _report_preflight_warning(report, lines):
    """As above, for the non-fatal version note."""
    for line in lines:
        try:
            report.Warning(line)
        except Exception:
            pass


def _flexicon_preflight(report):
    """
    Return True when flexicon is usable; otherwise report the problem and
    return False.

    Guarantees:
      * Never raises. A probe that itself throws is treated as "cannot
        determine" and returns True -- the pre-flight must never be the reason
        a working module stops running.
      * Silent when flexicon is current. No report call of any kind.
      * ASCII only, matching the [ERROR] prefix style used elsewhere here.

    The staleness GATE is hasattr(FLExProject, "FromOpenProject") -- a
    CAPABILITY probe, deliberately not a version comparison. A hardcoded
    version floor is a second source of truth that goes wrong the first release
    nobody remembers to raise, and the two version strings available can
    already disagree with each other on the same machine (an editable install
    reports one number in flexicon.version and another in package metadata).
    hasattr asks the only question that matters: is the bridge there.

    There IS a version comparison further down, and it is deliberately not a
    gate. It can only add a WARNING and can never change the return value:
    older-but-capable is a supported configuration, so the comparison being
    wrong costs a spurious note, never a working module. That is the whole
    reason a floor is refused here while a note is welcome.
    """
    try:
        if _flexicon is None:
            _report_preflight_error(report, [
                "[ERROR] This module needs flexicon, which is not installed in",
                "[ERROR] the Python environment FlexTools is using.",
                "[ERROR]",
                "[ERROR]   import failed with: %s" % (_FLEXICON_IMPORT_ERROR,),
                "[ERROR]",
                "[ERROR] To fix it, run this in the Python that FlexTools uses",
                "[ERROR] (which is not necessarily the one on your PATH):",
                "[ERROR]",
                "[ERROR]     pip install pyflexicon",
                "[ERROR]",
                "[ERROR] The module itself is fine -- nothing here needs editing.",
            ])
            return False

        if _FLEXICON_SYMBOL_ERROR is not None or FLExProject is None:
            # flexicon imported fine; one of the names in the import list at the
            # top of this file does not exist. This is the one pre-flight case
            # where the module IS what needs editing, so it must not borrow the
            # not-installed wording above.
            _report_preflight_error(report, [
                "[ERROR] flexicon is installed and working, but this module asks",
                "[ERROR] it for a name it does not export, so the module could",
                "[ERROR] not finish loading.",
                "[ERROR]",
                "[ERROR]   import failed with: %s" % (_FLEXICON_SYMBOL_ERROR,),
                "[ERROR]   flexicon version found: %s"
                % (_flexicon_installed_version(),),
                "[ERROR]",
                "[ERROR] Fix the `from flexicon import (...)` list near the top",
                "[ERROR] of this file -- remove or correct that name. Not every",
                "[ERROR] operations class has a top-level export: reversal work,",
                "[ERROR] for example, has no \"ReversalOperations\" -- reach it",
                "[ERROR] through project.ReversalIndexes / project.ReversalEntries.",
                "[ERROR]",
                "[ERROR] Nothing is wrong with your Python environment.",
            ])
            return False

        if not hasattr(FLExProject, "FromOpenProject"):
            _report_preflight_error(report, [
                "[ERROR] The flexicon installed for FlexTools is too old for",
                "[ERROR] this module: it has no FLExProject.FromOpenProject(),",
                "[ERROR] which is how the module attaches to the project",
                "[ERROR] FlexTools already opened.",
                "[ERROR]",
                "[ERROR]   version found: %s" % (_flexicon_installed_version(),),
                "[ERROR]",
                "[ERROR] To fix it, run this in the Python that FlexTools uses",
                "[ERROR] (which is not necessarily the one on your PATH):",
                "[ERROR]",
                "[ERROR]     pip install -U pyflexicon",
                "[ERROR]",
                "[ERROR] The module itself is fine -- nothing here needs editing.",
            ])
            return False

        # Past this point flexicon is usable and the module WILL run. What
        # follows is a note, not a gate: an older-but-capable flexicon is
        # supported, and the only thing worth saying is which versions are in
        # play, so that a later bug report starts with that fact rather than
        # discovering it.
        found = _flexicon_installed_version()
        if _flexicon_is_behind(found, _TESTED_AGAINST):
            _report_preflight_warning(report, [
                "[WARN] This module was generated against flexicon %s, and"
                % (_TESTED_AGAINST,),
                "[WARN] this environment has %s. Running anyway -- older is"
                % (found,),
                "[WARN] usually fine.",
                "[WARN]",
                "[WARN] If the module misbehaves, mention both versions in any",
                "[WARN] bug report, or bring the environment up to date with:",
                "[WARN]",
                "[WARN]     pip install -U pyflexicon",
            ])

    except Exception:
        # Fail open. If the probe cannot answer, let the module run and fail on
        # its own terms if it is going to; a broken diagnostic must not become
        # a broken module.
        return True

    return True


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
    if not _flexicon_preflight(report): return

    # Attach a flexicon facade to the project the host already opened. This is
    # the portable shape: under FlexTools `project` is a shallow flexlibs
    # FLExProject and this attaches the deep flexicon API to its live cache;
    # under the FlexToolsMCP runner `project` is already a flexicon
    # FLExProject and the call returns it unchanged. Same source, both hosts.
    #
    # Use `fx` from here on, wherever you would have written `project`.
    #
    # An attached view is a view over a cache it does not own, so: use
    # Transaction() (UndoableOperation() is refused), and do NOT call
    # SaveChanges() or CloseProject() -- the host owns the save. Just return
    # when you are done.
    fx = FLExProject.FromOpenProject(project)

    try:
        # ================================================================
        # Your implementation goes here
        # ================================================================

        # Example: Iterate entries
        report.Info("[INFO] Starting module execution...")

        # GetAll() returns a behavioral collection -- safe to loop, len(),
        # index/slice, or re-iterate freely. Only wrap in list(...) if you
        # specifically need a plain list (e.g. to hand off to code that
        # requires one).
        entries = fx.LexEntry.GetAll()
        report.Info(f"Found {len(entries)} lexical entries")

        # Example: Process each entry
        for i, entry in enumerate(entries):
            try:
                # Get entry form (headword)
                form = fx.LexEntry.GetLexemeForm(entry)

                # Get all senses for this entry (incl. subsenses, recursively).
                # NOTE two easy mistakes here (issue #84):
                #   - FLExProject has NO attribute named after the
                #     LexSenseOperations class; the sense accessor is
                #     project.Senses. Guessing raises AttributeError.
                #   - GetAllSenses exists on BOTH operations classes and they
                #     take DIFFERENT arguments: project.LexEntry.GetAllSenses
                #     takes an entry, project.Senses.GetAllSenses takes a
                #     SENSE (that sense plus its subsenses). Going from an
                #     entry, you want the LexEntry one.
                senses = fx.LexEntry.GetAllSenses(entry)
                report.Info(f"  [{i+1}] {form} ({len(senses)} senses)")

                # BuildGoToURL creates clickable links in FLExTools output
                # Users can click to jump directly to entry in FieldWorks GUI
                try:
                    entry_url = fx.BuildGotoURL(entry)
                    report.Info(f"      Goto entry: {entry_url}")
                except Exception:
                    # BuildGoToURL might not be available, continue anyway
                    pass

                # Process each sense
                for sense in senses:
                    gloss = fx.Senses.GetGloss(sense)
                    definition = fx.Senses.GetDefinition(sense)

                    if gloss:
                        report.Info(f"      - {gloss}")

                    # BuildGoToURL also works for senses
                    try:
                        sense_url = fx.BuildGotoURL(sense)
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
FLEXICON ADVANTAGES:
  - Handles "***" multistring normalization automatically
  - Comprehensive coverage of FieldWorks APIs (~90%)
  - Better error messages
  - Defensive casting for descriptor issues

COMMON PATTERNS:

1. Iterate entries:
   for entry in project.LexEntry.GetAll():
       form = project.LexEntry.GetLexemeForm(entry)

2. Get the senses of an entry -- use the LexEntry accessor:
   senses = project.LexEntry.GetAllSenses(entry)

   GetAllSenses exists on both operations classes and they take DIFFERENT
   arguments -- project.Senses.GetAllSenses(sense) takes a SENSE and returns
   that sense plus its subsenses. Starting from an entry, use the line above.
   (FLExProject also has no attribute named after the LexSenseOperations
   class, so project.<that name> raises AttributeError.)

3. Read sense fields via project.Senses -- these take a sense
   (flexicon returns "" not "***" for empty):
   gloss = project.Senses.GetGloss(sense)
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
