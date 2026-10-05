import unittest

from util.domain import EvaluationConfig, TrainingConfig


class ConfigurationTests(unittest.TestCase):
    def test_default_configurations_are_valid(self):
        TrainingConfig().validate()
        EvaluationConfig().validate()

    def test_invalid_training_configuration_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "epochs"):
            TrainingConfig(epochs=0).validate()

    def test_invalid_evaluation_configuration_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "episodes"):
            EvaluationConfig(episodes=0).validate()
