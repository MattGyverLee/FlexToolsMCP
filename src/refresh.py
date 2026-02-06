#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FlexTools MCP Index Refresh Script

Regenerates all API documentation indexes from source codebases.
Run this when LibLCM, FlexLibs stable, or FlexLibs 2.0 is updated.

Usage:
    python src/refresh.py                     # Refresh all indexes
    python src/refresh.py --flexlibs2-only    # Only refresh FlexLibs 2.0
    python src/refresh.py --flexlibs-only     # Only refresh FlexLibs stable
    python src/refresh.py --liblcm-only       # Only refresh LibLCM
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime


def load_env():
    """Load environment variables from .env file."""
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        print(f"[INFO] Loading configuration from {env_file}")
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())
    else:
        print("[WARN] No .env file found. Using defaults. Copy .env.example to .env to configure paths.")


# Load .env on import
load_env()


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent


def run_command(cmd: list, description: str) -> bool:
    """Run a command and return success status."""
    print(f"\n[INFO] {description}...")
    print(f"       Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=get_project_root(),
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print(f"[OK] {description} completed successfully")
            if result.stdout:
                # Print last few lines of output
                lines = result.stdout.strip().split('\n')
                for line in lines[-5:]:
                    print(f"     {line}")
            return True
        else:
            print(f"[ERROR] {description} failed")
            if result.stderr:
                print(f"        {result.stderr[:500]}")
            return False

    except Exception as e:
        print(f"[ERROR] {description} failed: {e}")
        return False


def refresh_flexlibs_stable(flexlibs_path: str = None) -> bool:
    """Refresh FlexLibs stable index."""
    if flexlibs_path is None:
        flexlibs_path = os.environ.get("FLEXLIBS_PATH", "D:/Github/flexlibs")

    output_path = get_project_root() / "index" / "flexlibs" / "flexlibs_api.json"

    cmd = [
        sys.executable,
        "src/flexlibs2_analyzer.py",
        "--flexlibs-path", flexlibs_path,
        "--output", str(output_path)
    ]

    return run_command(cmd, "Refreshing FlexLibs stable index")


def refresh_flexlibs2(flexlibs2_path: str = None) -> bool:
    """Refresh FlexLibs 2.0 index."""
    if flexlibs2_path is None:
        flexlibs2_path = os.environ.get("FLEXLIBS2_PATH", "D:/Github/flexlibs2")

    output_path = get_project_root() / "index" / "flexlibs" / "flexlibs2_api.json"

    cmd = [
        sys.executable,
        "src/flexlibs2_analyzer.py",
        "--flexlibs2-path", flexlibs2_path,
        "--output", str(output_path)
    ]

    return run_command(cmd, "Refreshing FlexLibs 2.0 index")


def refresh_liblcm(dll_path: str = None) -> bool:
    """Refresh LibLCM index."""
    if dll_path is None:
        dll_path = os.environ.get("FIELDWORKS_DLL_PATH")

    output_path = get_project_root() / "index" / "liblcm" / "liblcm_api.json"

    cmd = [
        sys.executable,
        "src/liblcm_extractor.py",
        "--output", str(output_path)
    ]

    if dll_path:
        cmd.extend(["--dll-path", dll_path])

    return run_command(cmd, "Refreshing LibLCM index")


def apply_categorization() -> bool:
    """Apply semantic categorization to LibLCM entities."""
    print("\n[INFO] Applying semantic categorization to LibLCM...")

    try:
        import json
        from collections import Counter

        liblcm_path = get_project_root() / "index" / "liblcm" / "liblcm_api.json"

        with open(liblcm_path, 'r', encoding='utf-8') as f:
            lcm = json.load(f)

        # Namespace-based categorization rules
        namespace_rules = {
            'SIL.LCModel.Core.Text': 'texts',
            'SIL.LCModel.Core.WritingSystems': 'writing_system',
            'SIL.LCModel.Core.SpellChecking': 'system',
            'SIL.LCModel.Core.Scripture': 'scripture',
            'SIL.LCModel.Core.Phonology': 'grammar',
            'SIL.LCModel.DomainServices.DataMigration': 'system',
            'SIL.LCModel.DomainServices.BackupRestore': 'system',
            'SIL.LCModel.Infrastructure.Impl': 'system',
            'SIL.LCModel.Infrastructure': 'system',
            'SIL.LCModel.Utils': 'system',
            'SIL.LCModel.Tools': 'system',
        }

        def categorize_entity(name, entity):
            current = entity.get('category', 'general')
            ns = entity.get('namespace', '')

            # Apply namespace rules
            for ns_pattern, cat in namespace_rules.items():
                if ns.startswith(ns_pattern):
                    return cat

            # Name-based rules
            name_lower = name.lower()

            # Prefix patterns
            if name.startswith('IMo') or name.startswith('Mo'):
                return 'grammar'
            if name.startswith('IPh') or name.startswith('Ph'):
                return 'grammar'
            if name.startswith('IFs') or name.startswith('Fs'):
                return 'grammar'
            if name.startswith('IWfi') or name.startswith('Wfi'):
                return 'wordform'
            if name.startswith('IDs') or name.startswith('Ds'):
                return 'discourse'
            if name.startswith('IRn') or name.startswith('Rn'):
                return 'notebook'
            if name.startswith('IScr') or name.startswith('Scr'):
                return 'scripture'
            if name.startswith('ISt') or name.startswith('St'):
                return 'texts'
            if name.startswith('IText') or name.startswith('Text'):
                return 'texts'
            if name.startswith('ILex') or name.startswith('Lex'):
                return 'lexicon'
            if name.startswith('IReversal') or name.startswith('Reversal'):
                return 'reversal'

            # Semantic name patterns
            if any(x in name_lower for x in ['sense', 'entry', 'lexeme', 'headword']):
                return 'lexicon'
            if any(x in name_lower for x in ['paragraph', 'footnote']):
                return 'texts'
            if any(x in name_lower for x in ['wordform', 'concordance']):
                return 'wordform'
            if any(x in name_lower for x in ['interlin', 'baseline']):
                return 'texts'

            # Compiler-generated
            if '<>c__' in name or name.startswith('Class_'):
                return 'internal'

            # Factory/Repository patterns
            if 'Factory' in name:
                return 'factory'
            if 'Repository' in name:
                return 'repository'

            return current

        # Apply recategorization
        changes = 0
        for name, entity in lcm.get('entities', {}).items():
            old_cat = entity.get('category', 'general')
            new_cat = categorize_entity(name, entity)
            if new_cat != old_cat:
                entity['category'] = new_cat
                changes += 1

        # Save updated file
        with open(liblcm_path, 'w', encoding='utf-8') as f:
            json.dump(lcm, f, indent=2, ensure_ascii=False)

        # Count categories
        categories = Counter()
        for entity in lcm.get('entities', {}).values():
            categories[entity.get('category', 'NONE')] += 1

        print(f"[OK] Recategorized {changes} entities")
        print("     Category counts:")
        for cat, count in categories.most_common(10):
            print(f"       {cat}: {count}")

        return True

    except Exception as e:
        print(f"[ERROR] Categorization failed: {e}")
        return False


def run_postprocess_reverse_mapping() -> bool:
    """Build reverse mapping from LibLCM to FlexLibs."""
    cmd = [
        sys.executable,
        "src/build_reverse_mapping.py",
        "--update-liblcm"
    ]
    return run_command(cmd, "Building reverse mapping (LibLCM -> FlexLibs)")


def run_postprocess_navigation_graph() -> bool:
    """Build navigation graph from LibLCM relationships."""
    cmd = [
        sys.executable,
        "src/build_navigation_graph.py",
        "--update-liblcm"
    ]
    return run_command(cmd, "Building navigation graph")


def run_postprocess_patterns() -> bool:
    """Extract common patterns from FlexLibs docstrings."""
    cmd = [
        sys.executable,
        "src/extract_patterns.py",
        "--update-flexlibs"
    ]
    return run_command(cmd, "Extracting common patterns")


def main():
    parser = argparse.ArgumentParser(
        description="Refresh FlexTools MCP API indexes"
    )
    parser.add_argument(
        "--flexlibs2-only",
        action="store_true",
        help="Only refresh FlexLibs 2.0 index"
    )
    parser.add_argument(
        "--flexlibs-only",
        action="store_true",
        help="Only refresh FlexLibs stable index"
    )
    parser.add_argument(
        "--liblcm-only",
        action="store_true",
        help="Only refresh LibLCM index"
    )
    parser.add_argument(
        "--flexlibs2-path",
        default="D:/Github/flexlibs2",
        help="Path to FlexLibs 2.0 repository"
    )
    parser.add_argument(
        "--flexlibs-path",
        default="D:/Github/flexlibs",
        help="Path to FlexLibs stable repository"
    )
    parser.add_argument(
        "--dll-path",
        help="Path to FieldWorks DLLs (auto-detected if not specified)"
    )
    parser.add_argument(
        "--skip-categorization",
        action="store_true",
        help="Skip semantic categorization step"
    )
    parser.add_argument(
        "--skip-postprocess",
        action="store_true",
        help="Skip post-processing (reverse mapping, navigation graph, patterns)"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("FlexTools MCP Index Refresh")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)

    success = True

    # Determine what to refresh
    only_one = args.flexlibs2_only or args.flexlibs_only or args.liblcm_only

    # Refresh FlexLibs stable
    if args.flexlibs_only or (not only_one):
        if not refresh_flexlibs_stable(args.flexlibs_path):
            success = False

    # Refresh FlexLibs 2.0
    if args.flexlibs2_only or (not only_one):
        if not refresh_flexlibs2(args.flexlibs2_path):
            success = False

    # Refresh LibLCM
    if args.liblcm_only or (not only_one):
        if not refresh_liblcm(args.dll_path):
            success = False
        elif not args.skip_categorization:
            if not apply_categorization():
                success = False

    # Post-processing steps (run if any indexes were refreshed)
    if not args.skip_postprocess and not only_one:
        print("\n" + "-" * 40)
        print("Post-processing...")
        print("-" * 40)

        # Build reverse mapping
        if not run_postprocess_reverse_mapping():
            success = False

        # Build navigation graph
        if not run_postprocess_navigation_graph():
            success = False

        # Extract patterns
        if not run_postprocess_patterns():
            success = False

    print("\n" + "=" * 60)
    if success:
        print("[OK] All indexes refreshed successfully")
    else:
        print("[WARN] Some indexes failed to refresh")
    print(f"Completed: {datetime.now().isoformat()}")
    print("=" * 60)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
