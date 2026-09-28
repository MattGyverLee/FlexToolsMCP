"""
id: rename-audio-files
intent: Rename audio files attached to entries based on a custom field value, updating both file on disk and FLEx reference
match_terms: ["rename audio files", "audio filename", "update audio links", "fix audio paths", "rename audio for entries"]
entities: ["LexEntry", "MoForm"]
operations: ["update"]
requires_write: true
origin: FLExTools modules RenameAudioFiles.py and FLExToolRenameAudio.py (Matthew Lee)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-dryrun"}
raw_lcm_lines: 0
notes: Renames audio files referenced by an entry's lexeme-form audio field and updates both the file on disk and the FLEx reference; the new filename comes from a custom field. Uses project.Allomorphs.GetFormAudio/SetFormAudio, which auto-detect the project's audio writing system and already return/accept a LinkedFiles-relative path. Handles Unicode normalization variants, filename sanitization, and on-disk collision detection, since flexicon has no file-rename wrapper. Actual disk renames only happen inside `if modifyAllowed:`; run with write_enabled=False first to review the dry-run report before enabling writes, since a rename that collides with an existing file is skipped but not otherwise validated.
"""
# --- PARAMS ---
CUSTOM_FIELD = "MediaFilename"  # Name of the custom field containing target filenames (case-sensitive)
# --- END PARAMS ---
import os
import re
import unicodedata

linked_files_dir = project.GetLinkedFilesDir()
report.Info(f"LinkedFiles directory: {linked_files_dir}")


def sanitize_filename(filename):
    """Remove OS-banned characters from filename"""
    banned_chars = r'[<>:"/\\|?*!&\']'
    sanitized = re.sub(banned_chars, "_", filename)
    sanitized = re.sub(r"_{2,}", "_", sanitized)
    return sanitized.strip("_ ")


def find_audio_file(directory, filename):
    """Find file in directory, handling Unicode normalization variations"""
    if not os.path.exists(directory):
        return None

    full_path = os.path.join(directory, filename)
    if os.path.exists(full_path):
        return full_path

    for norm_form in ["NFC", "NFD", "NFKC", "NFKD"]:
        normalized_filename = unicodedata.normalize(norm_form, filename)
        test_path = os.path.join(directory, normalized_filename)
        if os.path.exists(test_path):
            return test_path

    try:
        for f in os.listdir(directory):
            if f.lower() == filename.lower():
                return os.path.join(directory, f)
    except Exception:
        pass

    return None


# Process entries
entry_count = 0
audio_entries = 0
renamed_count = 0

for entry in project.LexEntry.GetAll():
    entry_count += 1

    # Lexeme form is the first item from Allomorphs.GetAll
    allo = next(iter(project.Allomorphs.GetAll(entry)), None)
    if not allo:
        continue

    audio_rel_path = project.Allomorphs.GetFormAudio(allo)
    if not audio_rel_path:
        continue

    audio_entries += 1
    current_audio_name = os.path.basename(audio_rel_path)
    audio_subdir = os.path.dirname(audio_rel_path.replace("LinkedFiles/", "").replace("LinkedFiles\\", ""))
    audio_dir = os.path.join(linked_files_dir, audio_subdir) if audio_subdir else linked_files_dir

    # Get custom field value for new filename
    new_filename = project.CustomFields.GetValue(entry, CUSTOM_FIELD)
    new_filename = str(new_filename).strip() if new_filename else ""
    if not new_filename:
        continue

    # Sanitize and add extension
    new_filename_sanitized = sanitize_filename(new_filename)
    if not new_filename_sanitized.lower().endswith(".wav"):
        new_filename_sanitized += ".wav"

    current_file_path = find_audio_file(audio_dir, current_audio_name)
    if not current_file_path:
        report.Warning(f"Entry {entry_count}: audio file not found: {current_audio_name}")
        continue

    current_dir = os.path.dirname(current_file_path)
    new_file_path = os.path.join(current_dir, new_filename_sanitized)

    if current_file_path == new_file_path:
        report.Info(f"Entry {entry_count}: audio already has correct name: {new_filename_sanitized}")
        continue

    if os.path.exists(new_file_path):
        report.Warning(f"Entry {entry_count}: target filename already exists: {new_filename_sanitized}")
        continue

    # Perform rename
    if modifyAllowed:
        try:
            os.rename(current_file_path, new_file_path)
            report.Info(f"Entry {entry_count}: renamed {os.path.basename(current_file_path)} -> {new_filename_sanitized}")

            new_rel_path = os.path.join(os.path.dirname(audio_rel_path), new_filename_sanitized).replace(os.sep, "/")
            project.Allomorphs.SetFormAudio(allo, new_rel_path)
            report.Info(f"Entry {entry_count}: updated audio link to {new_filename_sanitized}")
            renamed_count += 1
        except Exception as e:
            report.Error(f"Entry {entry_count}: failed to rename - {e}")
    else:
        report.Info(f"Entry {entry_count} (dry run): would rename {os.path.basename(current_file_path)} -> {new_filename_sanitized}")
        renamed_count += 1

# Summary
report.Info("=" * 50)
report.Info(f"SUMMARY:")
report.Info(f"  Entries scanned: {entry_count}")
report.Info(f"  Entries with audio: {audio_entries}")
report.Info(f"  Files processed: {renamed_count}")
if not modifyAllowed:
    report.Info(f"  Mode: READ-ONLY (dry run)")
report.Info("=" * 50)
