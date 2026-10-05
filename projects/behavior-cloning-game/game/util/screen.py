from util.colour import Colour

HUD_HEIGHT = 40


class Screen:
    def __init__(
        self,
        width=800,
        height=600,
        colour=Colour.WHITE,
        hud_height=HUD_HEIGHT,
    ) -> None:
        self.width = width
        self.height = height
        self.background = colour
        self.play_area_top = hud_height

    def center_width(self) -> float:
        return self.width / 2
    
    def center_height(self) -> float:
        return self.height / 2

    # Kept for compatibility with the original classroom examples.
    def CenterWidth(self) -> float:
        return self.center_width()

    def CenterHeight(self) -> float:
        return self.center_height()
