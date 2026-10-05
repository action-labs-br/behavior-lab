import unittest
from unittest.mock import Mock, call, patch

from util.colour import Colour
from util.display import Display
from util.rectangle import Rectangle
from util.screen import Screen


class DisplayTests(unittest.TestCase):
    def test_player_cannot_enter_reserved_hud_area(self):
        display = Display.__new__(Display)
        display.screen = Screen(width=100, height=100, hud_height=40)
        display.car = Rectangle(25, 39, 10, 10, Colour.BLOCK)

        self.assertTrue(display.is_car_out_of_bounds())

    def test_player_is_drawn_as_blue_circle_inside_its_bounding_box(self):
        display = Display.__new__(Display)
        display.gameDisplay = Mock()
        display.car = Rectangle(10, 20, 50, 50, Colour.BLOCK)

        with patch("util.display.pygame.draw.circle") as draw_circle:
            display.draw_car()

        draw_circle.assert_called_once_with(
            display.gameDisplay,
            Colour.BLOCK,
            (35, 45),
            25,
        )

    def test_target_is_white_with_black_border(self):
        display = Display.__new__(Display)
        display.gameDisplay = Mock()
        display.parking = Rectangle(10, 20, 70, 70, Colour.WHITE)

        with patch("util.display.pygame.draw.rect") as draw_rect:
            display.draw_parking()

        self.assertEqual(
            draw_rect.call_args_list,
            [
                call(display.gameDisplay, Colour.WHITE, [10, 20, 70, 70]),
                call(
                    display.gameDisplay,
                    Colour.BLACK,
                    [10, 20, 70, 70],
                    width=3,
                ),
            ],
        )

    def test_hud_is_white_with_black_border(self):
        display = Display.__new__(Display)
        display.gameDisplay = Mock()
        display.screen = Screen(width=800, height=600, hud_height=40)
        text_surface = Mock()
        text_rectangle = Mock()

        with (
            patch("util.display.pygame.draw.rect") as draw_rect,
            patch("util.display.pygame.font.Font"),
            patch.object(
                display,
                "text_objects",
                return_value=(text_surface, text_rectangle),
            ),
        ):
            display.draw_hud("Controls")

        self.assertEqual(
            draw_rect.call_args_list,
            [
                call(display.gameDisplay, Colour.WHITE, [0, 0, 800, 40]),
                call(
                    display.gameDisplay,
                    Colour.BLACK,
                    [0, 0, 800, 40],
                    width=2,
                ),
            ],
        )
        display.gameDisplay.blit.assert_called_once_with(text_surface, text_rectangle)


if __name__ == "__main__":
    unittest.main()
