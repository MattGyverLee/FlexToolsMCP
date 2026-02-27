#
#   Clean Up Glosses
#    - A FlexTools Module -
#
#   Scans all glosses, finds periods between two letters and replaces them with spaces
#
#   API Target: flexlibs2
#   Platforms: Python .NET and IronPython
#

import re
from flextoolslib import *

#----------------------------------------------------------------
# Configuration

DRY_RUN = True  # Set to False to actually make changes

#----------------------------------------------------------------
# Documentation that the user sees:

docs = {FTM_Name        : "Clean Up Glosses",
        FTM_Version     : 1,
        FTM_ModifiesDB  : True,
        FTM_Synopsis    : "Scans all glosses, finds periods between two letters and replaces them with spaces",
        FTM_Description :
"""
Scans all glosses in the lexicon and finds periods (.) that appear between
two letters (e.g., "a.b" becomes "a b"). This is useful for cleaning up
glosses that may have been imported with incorrect formatting.

Set DRY_RUN = True to preview changes without modifying the database.
Set DRY_RUN = False to apply the changes.
""" }

#----------------------------------------------------------------
# Regex pattern: matches a period between two word characters
# Uses lookbehind (?<=\w) and lookahead (?=\w) to match only the period

PERIOD_BETWEEN_LETTERS = re.compile(r'(?<=\w)\.(?=\w)')

#----------------------------------------------------------------
# The main processing function

def Main(project, report, modifyAllowed):
    """
    Main entry point for the FlexTools module.

    Args:
        project: FLExProject instance providing access to the FieldWorks database
        report: Reporter object for logging (report.Info, report.Warning, report.Error)
        modifyAllowed: Boolean indicating if database modifications are permitted
    """
    if DRY_RUN:
        report.Warning("DRY RUN mode - no changes will be made")
    elif not modifyAllowed:
        report.Error("This module requires write access. Enable 'Modify' in Run settings.")
        return

    report.Info("Scanning all senses for glosses with periods between letters...")

    senses_checked = 0
    glosses_to_fix = 0
    glosses_fixed = 0

    # Iterate through all senses in the project
    for sense in project.Senses.GetAll():
        senses_checked += 1

        # Get the current gloss
        gloss = project.Senses.GetGloss(sense)

        if not gloss:
            continue

        # Check if the gloss has a period between letters
        if PERIOD_BETWEEN_LETTERS.search(gloss):
            # Get entry info for reporting
            entry = project.Senses.GetOwningEntry(sense)
            headword = project.Entries.GetHeadword(entry) if entry else "<unknown>"
            sense_num = project.Senses.GetSenseNumber(sense)

            # Create the fixed gloss
            new_gloss = PERIOD_BETWEEN_LETTERS.sub(' ', gloss)

            glosses_to_fix += 1

            report.Info(f"  {headword} (sense {sense_num}): '{gloss}' -> '{new_gloss}'")

            if not DRY_RUN and modifyAllowed:
                project.Senses.SetGloss(sense, new_gloss)
                glosses_fixed += 1

    # Summary
    report.Info("---")
    report.Info(f"Senses checked: {senses_checked}")
    report.Info(f"Glosses needing fix: {glosses_to_fix}")

    if DRY_RUN:
        report.Warning(f"DRY RUN complete. Set DRY_RUN = False to apply {glosses_to_fix} changes.")
    else:
        report.Info(f"Glosses fixed: {glosses_fixed}")
        report.Info("Done.")


#----------------------------------------------------------------

FlexToolsModule = FlexToolsModuleClass(Main, docs)

#----------------------------------------------------------------
if __name__ == '__main__':
    print(FlexToolsModule.Help())
