import random
import sys
from typing import TextIO

import pygame

from util.coordinate import Coordinate
from util.data import Demonstration, EpisodeRecorder
from util.display import Display
from util.domain import Action, EpisodeOutcome, EpisodeResult, GameMode, GameState
from util.inputs import FromKeyboard


class Game:
    """Run independent episodes without growing the Python call stack."""

    def __init__(
        self,
        input=None,
        output: TextIO = sys.stdout,
        *,
        display=None,
        seed: int | None = None,
        framerate: int = 60,
        staleness_factor: int = 100,
        recorder: EpisodeRecorder | None = None,
        max_steps: int | None = None,
        round_delay_ms: int = 1000,
        mode: GameMode = GameMode.COLLECTION,
    ) -> None:
        pygame.init()
        self.input = input if input is not None else FromKeyboard()
        self.display = display if display is not None else Display()
        self.clock = pygame.time.Clock()
        self.framerate = framerate
        self.staleness_factor = staleness_factor
        self.output = output
        self.recorder = recorder
        self.max_steps = max_steps
        self.round_delay_ms = round_delay_ms
        self.mode = mode
        self.episode_limit: int | None = None
        self.num_success = 0
        self._game_exit = False
        self._random = random.Random(seed)
        self.display.set_caption("Parking game")

    def is_game_ended(self) -> bool:
        return self._game_exit

    def update_clock(self) -> None:
        self.clock.tick(self.framerate)

    def _wait_between_rounds(self) -> None:
        if self.round_delay_ms <= 0:
            return
        deadline = pygame.time.get_ticks() + self.round_delay_ms
        while not self._game_exit and pygame.time.get_ticks() < deadline:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (
                    event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
                ):
                    self._game_exit = True
                    break
            self.clock.tick(60)

    def fail(self) -> None:
        self.display.message_display("Failed")

    def success(self) -> None:
        self.display.message_display("Success")

    def _hud_text(self, episode_id: int | None) -> str:
        episode = str(episode_id or "-")
        if self.episode_limit is not None:
            episode = f"{episode}/{self.episode_limit}"

        if self.mode == GameMode.EVALUATION:
            return (
                "MODEL EVALUATION | Esc Finish | "
                f"Attempt {episode} | Successes {self.num_success}"
            )

        samples = self.recorder.written_samples if self.recorder is not None else 0
        completed = self.recorder.completed_episodes if self.recorder is not None else 0
        paused = " | PAUSED" if getattr(self.input, "paused", False) else ""
        return (
            "COLLECT | Arrows Move | Space Pause | Esc Finish | "
            f"Ep {episode} | Done {completed} | Samples {samples}{paused}"
        )

    def render(self, episode_id: int | None = None) -> None:
        self.display.set_background()
        self.display.draw_parking()
        self.display.draw_car()
        if hasattr(self.display, "draw_hud"):
            self.display.draw_hud(self._hud_text(episode_id))

    def _reset_episode(self) -> None:
        self.input.reset_move()
        car_x = (self.display.screen.width - self.display.car.w) / 2
        car_y = (self.display.screen.height - self.display.car.h) / 2
        self.display.car.teleport(Coordinate(car_x, car_y))
        self.input.goto(car_x, car_y)

        target_x = self._random.randint(0, self.display.screen.width - self.display.parking.w)
        target_y = self._random.randint(
            self.display.screen.play_area_top,
            self.display.screen.height - self.display.parking.h,
        )
        self.display.parking.teleport(Coordinate(target_x, target_y))
        self.input.move_target(target_x, target_y)

    def run_episode(self, episode_id: int) -> EpisodeResult:
        self._reset_episode()
        stalled = 0
        steps = 0

        while not self._game_exit:
            state = GameState(
                self.display.car.pos.x,
                self.display.car.pos.y,
                self.display.parking.pos.x,
                self.display.parking.pos.y,
            )
            move = self.input.get_move()
            if getattr(self.input, "quit_requested", False):
                self._game_exit = True
                if self.recorder is not None:
                    self.recorder.discard_episode()
                return EpisodeResult(episode_id, EpisodeOutcome.QUIT, steps)

            if getattr(self.input, "paused", False):
                self.render(episode_id)
                pygame.display.update()
                self.update_clock()
                continue

            self.display.car.step(move)
            steps += 1
            if self.recorder is not None:
                self.recorder.record(
                    Demonstration(
                        episode_id=episode_id,
                        step=steps - 1,
                        elapsed_ms=pygame.time.get_ticks(),
                        state=state,
                        action=Action(move.x, move.y),
                    )
                )
            stalled = stalled + 1 if move == Coordinate(0, 0) else 0
            self.render(episode_id)

            outcome = None
            if self.display.is_car_inside_parking():
                self.num_success += 1
                self.success()
                outcome = EpisodeOutcome.SUCCESS
            elif self.display.is_car_out_of_bounds():
                self.fail()
                outcome = EpisodeOutcome.OUT_OF_BOUNDS
            elif stalled > self.staleness_factor:
                self.fail()
                outcome = EpisodeOutcome.STALLED
            elif self.max_steps is not None and steps >= self.max_steps:
                self.fail()
                outcome = EpisodeOutcome.STALLED

            print(
                f"{episode_id},{pygame.time.get_ticks()},{self.display.car},"
                f"{self.display.parking},{move}",
                file=self.output,
            )
            pygame.display.update()
            self.update_clock()

            if outcome is not None:
                if self.recorder is not None:
                    self.recorder.finish_episode(outcome)
                rate = 100 * self.num_success / episode_id
                print(f"{episode_id}: {rate:.2f}%")
                self._wait_between_rounds()
                return EpisodeResult(episode_id, outcome, steps)

        return EpisodeResult(episode_id, EpisodeOutcome.QUIT, steps)

    def start(self, execution_id: int = 0, max_episodes: int | None = None) -> list[EpisodeResult]:
        self.episode_limit = max_episodes
        results = []
        while not self._game_exit and (max_episodes is None or len(results) < max_episodes):
            execution_id += 1
            result = self.run_episode(execution_id)
            results.append(result)
            if result.outcome == EpisodeOutcome.QUIT:
                break
        return results

    def quit(self) -> None:
        self._game_exit = True
        pygame.quit()


if __name__ == "__main__":
    pass
