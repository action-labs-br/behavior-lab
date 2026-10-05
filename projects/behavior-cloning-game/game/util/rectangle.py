from math import sqrt
import pygame

from util.colour import Colour
from util.coordinate import Coordinate

class Rectangle():
    def __init__(self, x=0, y=0, w=0, h=0, colour=Colour.BLACK) -> None:
        self.x = x
        self.y = y
        self.pos = Coordinate(x, y)
        self.w = w
        self.h = h
        self.colour = colour

    def dim(self) -> list:
        return [ self.pos.x, self.pos.y, self.w, self.h ]
    
    def draw(self, display: object) -> None:
        pygame.draw.rect(display, self.colour, self.dim())

    def step(self, delta: object) -> None:
        self.pos += delta

    def teleport(self, position: object) -> None:
        self.pos = Coordinate(position.x, position.y)

    def __str__(self) -> str:
        return f"{self.pos.x},{self.pos.y}"
    
    def center(self) -> object:
        x = self.pos.x + self.w / 2
        y = self.pos.y + self.h / 2
        return Coordinate(x,y)
    

    def distance(self, other) -> object:
        a = self.center()
        b = other.center()
        return sqrt((b.x - a.x)**2 + (b.y - a.y)**2)
