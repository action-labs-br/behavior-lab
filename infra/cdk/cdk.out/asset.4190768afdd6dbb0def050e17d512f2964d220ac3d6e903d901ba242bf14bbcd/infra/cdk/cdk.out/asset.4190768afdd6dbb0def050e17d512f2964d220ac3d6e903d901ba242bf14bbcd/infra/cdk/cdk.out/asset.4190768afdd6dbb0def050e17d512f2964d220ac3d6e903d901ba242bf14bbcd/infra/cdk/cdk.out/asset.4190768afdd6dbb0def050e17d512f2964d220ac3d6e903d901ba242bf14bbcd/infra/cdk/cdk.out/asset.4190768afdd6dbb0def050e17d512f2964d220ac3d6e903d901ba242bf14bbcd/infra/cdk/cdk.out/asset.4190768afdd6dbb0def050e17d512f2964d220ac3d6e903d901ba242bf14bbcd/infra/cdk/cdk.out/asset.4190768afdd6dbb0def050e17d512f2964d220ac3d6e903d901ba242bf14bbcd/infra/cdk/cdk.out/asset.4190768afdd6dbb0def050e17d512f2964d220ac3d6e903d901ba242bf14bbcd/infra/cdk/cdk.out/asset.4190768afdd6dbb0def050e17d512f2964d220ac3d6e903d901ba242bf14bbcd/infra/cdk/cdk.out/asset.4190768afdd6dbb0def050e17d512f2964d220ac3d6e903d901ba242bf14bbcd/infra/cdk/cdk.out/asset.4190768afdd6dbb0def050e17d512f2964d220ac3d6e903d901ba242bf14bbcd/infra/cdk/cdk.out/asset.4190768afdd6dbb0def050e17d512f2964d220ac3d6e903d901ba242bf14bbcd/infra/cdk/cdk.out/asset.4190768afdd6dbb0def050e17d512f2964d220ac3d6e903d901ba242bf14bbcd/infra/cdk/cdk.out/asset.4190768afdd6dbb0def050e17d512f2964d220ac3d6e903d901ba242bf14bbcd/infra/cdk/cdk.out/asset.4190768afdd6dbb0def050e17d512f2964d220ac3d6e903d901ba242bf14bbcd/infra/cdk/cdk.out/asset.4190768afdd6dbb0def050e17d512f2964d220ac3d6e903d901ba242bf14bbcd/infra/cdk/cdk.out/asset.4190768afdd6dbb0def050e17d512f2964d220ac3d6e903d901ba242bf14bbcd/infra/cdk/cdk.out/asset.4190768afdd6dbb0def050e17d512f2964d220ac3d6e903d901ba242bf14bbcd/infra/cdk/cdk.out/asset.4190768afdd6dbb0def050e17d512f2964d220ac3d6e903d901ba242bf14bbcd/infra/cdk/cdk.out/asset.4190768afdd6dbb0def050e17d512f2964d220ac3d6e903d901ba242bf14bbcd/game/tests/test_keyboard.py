import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pygame

from util.inputs import FromKeyboard


class KeyboardTests(unittest.TestCase):
    def test_space_toggles_pause_without_movement(self):
        keyboard = FromKeyboard()
        event = SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_SPACE)
        with patch("util.inputs.pygame.event.get", return_value=[event]):
            move = keyboard.get_move()
        self.assertTrue(keyboard.paused)
        self.assertEqual((move.x, move.y), (0, 0))

    def test_escape_requests_clean_session_finish(self):
        keyboard = FromKeyboard()
        event = SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_ESCAPE)
        with patch("util.inputs.pygame.event.get", return_value=[event]):
            move = keyboard.get_move()
        self.assertTrue(keyboard.quit_requested)
        self.assertEqual((move.x, move.y), (0, 0))
