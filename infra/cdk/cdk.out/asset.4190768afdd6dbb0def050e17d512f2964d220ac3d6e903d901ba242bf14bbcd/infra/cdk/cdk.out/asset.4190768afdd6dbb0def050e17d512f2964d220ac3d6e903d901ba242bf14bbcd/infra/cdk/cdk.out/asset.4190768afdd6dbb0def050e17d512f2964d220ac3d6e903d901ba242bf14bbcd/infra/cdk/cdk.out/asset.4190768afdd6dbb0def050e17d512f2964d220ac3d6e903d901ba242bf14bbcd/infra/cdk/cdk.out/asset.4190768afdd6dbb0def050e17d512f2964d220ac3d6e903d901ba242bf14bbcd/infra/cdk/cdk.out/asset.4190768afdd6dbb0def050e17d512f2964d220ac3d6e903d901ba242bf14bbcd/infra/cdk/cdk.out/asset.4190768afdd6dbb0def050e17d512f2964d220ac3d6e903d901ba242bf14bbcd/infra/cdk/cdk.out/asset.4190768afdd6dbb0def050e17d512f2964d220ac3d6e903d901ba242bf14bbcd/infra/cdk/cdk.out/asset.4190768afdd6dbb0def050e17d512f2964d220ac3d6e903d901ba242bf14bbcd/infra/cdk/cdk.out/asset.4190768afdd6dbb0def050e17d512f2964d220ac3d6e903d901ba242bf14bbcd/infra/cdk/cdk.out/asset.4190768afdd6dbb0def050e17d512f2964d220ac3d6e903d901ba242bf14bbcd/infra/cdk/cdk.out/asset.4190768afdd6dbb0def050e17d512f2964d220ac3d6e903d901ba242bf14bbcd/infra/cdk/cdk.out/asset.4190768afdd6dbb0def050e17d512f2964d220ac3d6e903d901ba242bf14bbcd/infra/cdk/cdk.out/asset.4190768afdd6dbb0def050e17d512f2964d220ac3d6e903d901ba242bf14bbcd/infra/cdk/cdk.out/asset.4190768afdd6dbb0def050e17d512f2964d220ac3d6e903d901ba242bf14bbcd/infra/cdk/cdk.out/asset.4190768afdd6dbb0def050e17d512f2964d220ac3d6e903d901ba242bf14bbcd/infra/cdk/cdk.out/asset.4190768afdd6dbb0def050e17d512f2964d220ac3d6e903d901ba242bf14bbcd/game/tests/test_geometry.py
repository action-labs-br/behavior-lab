import unittest

from util.coordinate import Coordinate
from util.rectangle import Rectangle


class RectangleTests(unittest.TestCase):
    def test_center_tracks_teleported_position(self):
        rectangle = Rectangle(1, 2, 10, 20)
        rectangle.teleport(Coordinate(30, 40))

        self.assertEqual(rectangle.center(), Coordinate(35, 50))

    def test_teleport_copies_the_coordinate(self):
        destination = Coordinate(10, 20)
        rectangle = Rectangle()
        rectangle.teleport(destination)
        destination.x = 99

        self.assertEqual(rectangle.pos, Coordinate(10, 20))


if __name__ == "__main__":
    unittest.main()
