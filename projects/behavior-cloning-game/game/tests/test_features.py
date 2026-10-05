import unittest

from util.domain import GameState
from util.features import get_feature_transform


class FeatureTransformTests(unittest.TestCase):
    def test_absolute_preserves_raw_coordinates(self):
        state = GameState(375, 275, 120, 130)
        self.assertEqual(
            get_feature_transform("absolute").apply(state),
            (375, 275, 120, 130),
        )

    def test_relative_center_uses_normalized_shape_centers(self):
        state = GameState(375, 275, 120, 130)
        result = get_feature_transform("relative-center").apply(state)
        self.assertAlmostEqual(result[0], -245 / 800)
        self.assertAlmostEqual(result[1], -135 / 600)

    def test_relative_containment_is_zero_anywhere_inside_valid_interval(self):
        transform = get_feature_transform("relative-containment")
        self.assertEqual(transform.apply(GameState(110, 210, 100, 200)), (0, 0))

    def test_relative_containment_points_to_nearest_valid_position(self):
        result = get_feature_transform("relative-containment").apply(
            GameState(150, 150, 100, 200)
        )
        self.assertAlmostEqual(result[0], -30 / 800)
        self.assertAlmostEqual(result[1], 50 / 600)

    def test_unknown_transform_has_actionable_error(self):
        with self.assertRaisesRegex(ValueError, "choose one of"):
            get_feature_transform("mystery")


if __name__ == "__main__":
    unittest.main()
