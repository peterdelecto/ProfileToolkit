"""Shared pytest fixtures and tkinter mocking for all test modules."""

import os
import sys
import tempfile
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Build a tkinter mock that satisfies both `import tkinter as tk` and
# `from tkinter import ttk, filedialog, messagebox`.
tk_mock = mock.MagicMock()
tk_mock.__name__ = "tkinter"
tk_mock.__package__ = "tkinter"
tk_mock.__path__ = []
tk_mock.__spec__ = None

ttk_mock = mock.MagicMock()
ttk_mock.__name__ = "tkinter.ttk"
ttk_mock.__package__ = "tkinter"

filedialog_mock = mock.MagicMock()
filedialog_mock.__name__ = "tkinter.filedialog"
filedialog_mock.__package__ = "tkinter"

messagebox_mock = mock.MagicMock()
messagebox_mock.__name__ = "tkinter.messagebox"
messagebox_mock.__package__ = "tkinter"

tk_mock.ttk = ttk_mock
tk_mock.filedialog = filedialog_mock
tk_mock.messagebox = messagebox_mock


# Make tk.Frame and tk.Toplevel real (stub) classes so that subclasses like
# ProfileDetailPanel are real Python types and can be instantiated with object.__new__().
class _FakeTkBase:
    def __init__(self, *args, **kwargs):
        pass

    def winfo_toplevel(self):
        return self

    def bind(self, *args, **kwargs):
        pass


tk_mock.Frame = _FakeTkBase
tk_mock.Toplevel = _FakeTkBase
tk_mock.Tk = _FakeTkBase

tkfont_mock = mock.MagicMock()
tkfont_mock.__name__ = "tkinter.font"
tkfont_mock.__package__ = "tkinter"

sys.modules["tkinter"] = tk_mock
sys.modules["tkinter.ttk"] = ttk_mock
sys.modules["tkinter.filedialog"] = filedialog_mock
sys.modules["tkinter.messagebox"] = messagebox_mock
sys.modules["tkinter.font"] = tkfont_mock
