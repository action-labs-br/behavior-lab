class Coordinate:
    def __init__(self, x, y) -> None:
        self.x = x
        self.y = y

    def __str__(self) -> str:
        return f"{self.x},{self.y}"
    
    def __add__(self, other):
        return Coordinate(self.x+other.x, self.y+other.y)

    def __sub__(self, other):
        return Coordinate(self.x-other.x, self.y-other.y)
    
    def __eq__(self, other):
        return self.x == other.x and self.y == other.y
    

if __name__=='__main__':
    pass
