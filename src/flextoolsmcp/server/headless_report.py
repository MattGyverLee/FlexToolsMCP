#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HeadlessReport - FLExTools-compatible reporter for headless/MCP execution.

This mimics FLExTools's FTReporter pattern, allowing module code to be
completely unchanged whether running in the FLExTools GUI (with UI handler)
or headless via MCP (collecting messages in a list).

Module code can use identical patterns in both contexts:
    report.Info("message")
    report.Warning("warning")
    report.Error("error")
"""

import sys
import codecs


class HeadlessReport:
    """
    Drop-in Report replacement for headless execution.

    Mimics FLExTools FTReporter API. Messages are collected in a list
    and printed to console. Module code is identical whether running in
    FLExTools GUI or MCP headless.
    """

    def __init__(self):
        """Initialize reporter with empty message list and UTF-8 console encoding."""
        self.messages = []

        # Ensure UTF-8 console output for headless execution
        # This is critical for multilingual data (IPA, tones, etc.)
        if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
        if sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)

    @staticmethod
    def _normalize_message(msg):
        """Ensure message is a string (convert non-string types via repr)."""
        if not isinstance(msg, (str, type(None))):
            return repr(msg)
        return msg

    def Info(self, msg, ref=None):
        """
        Report informational message.

        Args:
            msg: Message text (str or convertible to str)
            ref: Optional reference (e.g., FLEx URL or additional context)
        """
        msg = self._normalize_message(msg)
        self.messages.append(("INFO", msg, ref))
        print(f"[INFO] {msg}")
        if ref:
            print(f"       {ref}")

    def Warning(self, msg, ref=None):
        """
        Report warning message.

        Args:
            msg: Message text
            ref: Optional reference
        """
        msg = self._normalize_message(msg)
        self.messages.append(("WARNING", msg, ref))
        print(f"[WARN] {msg}")
        if ref:
            print(f"       {ref}")

    def Error(self, msg, ref=None):
        """
        Report error message.

        Args:
            msg: Message text
            ref: Optional reference
        """
        msg = self._normalize_message(msg)
        self.messages.append(("ERROR", msg, ref))
        print(f"[ERROR] {msg}")
        if ref:
            print(f"        {ref}")

    def Blank(self):
        """Report a blank line."""
        self.messages.append(("BLANK", None, None))
        print()

    def Debug(self, msg, ref=None):
        """
        Report debug message (only shown if DEBUG env var set).

        Args:
            msg: Message text
            ref: Optional reference
        """
        import os

        msg = self._normalize_message(msg)
        self.messages.append(("DEBUG", msg, ref))
        if os.getenv("DEBUG"):
            print(f"[DEBUG] {msg}")
            if ref:
                print(f"        {ref}")
