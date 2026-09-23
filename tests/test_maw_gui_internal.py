"""Frozen app internal commands must not lose their child-process flags."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import maw_gui


class InternalCommandTests(unittest.TestCase):
    def test_editor_server_receives_explicit_port(self) -> None:
        with patch("maw_gui._run_internal_serve", return_value=0) as serve:
            result = maw_gui.main(["--serve", "--blank", "--no-open", "--port", "54321"])
        self.assertEqual(result, 0)
        serve.assert_called_once_with(["--blank", "--no-open", "--port", "54321"])

    def test_editor_server_allows_ephemeral_port(self) -> None:
        with patch("maw_gui._run_internal_serve", return_value=0) as serve:
            maw_gui.main(["--serve", "--blank", "--port", "0"])
        serve.assert_called_once_with(["--blank", "--port", "0"])


if __name__ == "__main__":
    unittest.main()
