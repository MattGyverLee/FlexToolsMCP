# Recovery: restoring a project from an automatic pre-write backup

Issue #55 (Rung 2) added an **automatic pre-write backup**: before the FIRST
mutating `flextools_run_module()` call per (MCP session, project), the
server copies the project's `.fwdata` file to a timestamped directory under:

```
~/.flextoolsmcp/backups/<project-name>/<UTC-timestamp>/<project-name>.fwdata
```

`<UTC-timestamp>` uses the form `YYYYMMDDTHHMMSSZ` (e.g. `20260720T143012Z`),
so listing a project's backup directory and sorting by name also sorts
chronologically.

Only the newest 5 backups per project are kept; older ones are pruned
automatically. Configure retention with:

```
flextools_manage_config(action="set", key="backup_retention", value=10)
```

Opt out of the automatic backup entirely (not recommended) with:

```
flextools_manage_config(action="set", key="backup_before_write", value=false)
```

or per-call: `flextools_run_module(..., backup_before_write=false)`.

The backup is skipped (with a `WARNING` in `operations.log`) if free disk
space on the backup volume is under 2x the project's `.fwdata` size.

## Restore is manual, on purpose

**There is no automated restore tool.** Restoring a backup means overwriting
a live project file -- the one operation that must never be easy to invoke
by accident. Restoring is a deliberate, manual, human-supervised procedure:

### Steps to restore a backup

1. **Close FieldWorks completely.** FieldWorks must not have the project
   open (in any window, on any machine, if the project lives on a shared
   drive). Restoring over a project FieldWorks has open will corrupt it.

2. **Locate the backup you want.** List the project's backup directory:

   ```
   dir "%USERPROFILE%\.flextoolsmcp\backups\<project-name>"
   ```

   Pick the timestamp you want to restore to. Each subdirectory contains one
   `<project-name>.fwdata` file, a point-in-time copy.

3. **Locate the live project file.** Ask `flextools_list_projects` for the
   canonical location, or check
   `%ProgramData%\SIL\FieldWorks 9\ProjectsDir.txt`. The live file is:

   ```
   <ProjectsDir>\<project-name>\<project-name>.fwdata
   ```

4. **Back up the CURRENT (possibly-broken) file first**, just in case:

   ```
   copy "<ProjectsDir>\<project-name>\<project-name>.fwdata" "<ProjectsDir>\<project-name>\<project-name>.fwdata.before-restore"
   ```

5. **Copy the backup file over the live file:**

   ```
   copy "%USERPROFILE%\.flextoolsmcp\backups\<project-name>\<timestamp>\<project-name>.fwdata" "<ProjectsDir>\<project-name>\<project-name>.fwdata"
   ```

   Confirm the overwrite when prompted.

6. **Reopen the project in FieldWorks** (or via `flextools_start` +
   `flextools_run_module`) and verify the data is what you expect.

### If the writing-system store also needs restoring

The current backup implementation copies `.fwdata` only, not any sibling
writing-system store directory. If your project's writing systems changed
between the backup timestamp and now, you may need to reconcile those
separately (FieldWorks -> Tools -> Configure -> Writing Systems) after
restoring the `.fwdata` file. A future issue may extend the backup to
include the writing-system store when it's trivially copyable.

## Why not automate this?

An automated "restore" tool would need write access to a location that may
be a live, shared, network-mounted project -- and a single bad argument
(wrong project name, wrong timestamp) would silently destroy current work
with no confirmation step in between. Manual restore forces a human to look
at the timestamp, look at the target path, and make the call. If you need
this automated for a specific, supervised workflow, open an issue describing
the safety constraints you'd want (confirmation prompts, dry-run diff,
mandatory backup-of-current-before-restore, etc.) -- see the `Related`
section of issue #55.
