import pygame

from util.screen import Screen
from util.rectangle import Rectangle
from util.colour import Colour

class Display:
    def __init__(self) -> None:
        self.screen = Screen()
        self.gameDisplay = pygame.display.set_mode((self.screen.width,self.screen.height))
        self.car = Rectangle((self.screen.width * 0.45),(self.screen.height * 0.8),50,50,Colour.BLOCK)
        self.parking = Rectangle(0, 0, 70, 70, Colour.WHITE)

    def set_caption(self, text: str) -> None:
        pygame.display.set_caption(text)

    def set_background(self) -> None:
        self.gameDisplay.fill(self.screen.background)

    def get(self) -> object:
        return self.gameDisplay
    
    def draw_car(self) -> None:
        radius = min(self.car.w, self.car.h) // 2
        center = (
            round(self.car.pos.x + self.car.w / 2),
            round(self.car.pos.y + self.car.h / 2),
        )
        pygame.draw.circle(self.gameDisplay, self.car.colour, center, radius)

    def draw_parking(self) -> None:
        self.parking.draw(self.gameDisplay)
        pygame.draw.rect(
            self.gameDisplay,
            Colour.BLACK,
            self.parking.dim(),
            width=3,
        )

    def text_objects(self, text, font):
        textSurface = font.render(text, True, Colour.BLACK)
        return textSurface, textSurface.get_rect()

    def message_display(self, text):
        largeText = pygame.font.Font(None, 72)
        TextSurf, TextRect = self.text_objects (text, largeText)
        TextRect.center = (self.screen.CenterWidth(), self.screen.CenterHeight())
        self.gameDisplay.blit(TextSurf, TextRect)

    def draw_hud(self, text: str) -> None:
        hud_rectangle = [0, 0, self.screen.width, self.screen.play_area_top]
        pygame.draw.rect(self.gameDisplay, Colour.WHITE, hud_rectangle)
        pygame.draw.rect(
            self.gameDisplay,
            Colour.BLACK,
            hud_rectangle,
            width=2,
        )
        font = pygame.font.Font(None, 18)
        surface, rectangle = self.text_objects(text, font)
        rectangle.topleft = (10, 10)
        self.gameDisplay.blit(surface, rectangle)

    def is_car_inside_parking(self) -> bool:
        return (self.car.pos.x >= self.parking.pos.x) and (self.car.pos.x+self.car.w <= self.parking.pos.x+self.parking.w) and \
                (self.car.pos.y >= self.parking.pos.y) and (self.car.pos.y+self.car.h <= self.parking.pos.y+self.parking.h)

    def is_car_out_of_bounds(self) -> bool:
        return (self.car.pos.x > self.screen.width - self.car.w or self.car.pos.x < 0) or \
                (self.car.pos.y > self.screen.height - self.car.h or \
                 self.car.pos.y < self.screen.play_area_top)
