import PIL
import abc
from typing import List, Tuple, Union, Iterable
from PIL import Image, ImageDraw, ImageFont

class BaseElement(abc.ABC):
    def __init__(self, box:Union[Iterable[int],Iterable[float]] = (0, 0, 0, 0)):
        self.box = [float(i) for i in box]
        self.ux = None
        self.ly = None
        self.dx = None
        self.ry = None
        self.hight = None
        self.width = None
        self.image = None
        self.position = (self.ux, self.ly)
        self.size = (self.width, self.hight)

    @abc.abstractmethod
    def render(self):
        raise NotImplementedError
    
    def get_box(self):
        return self.box
    
    def set_box(self, box:Tuple[float, float, float, float]):
        self.box = box
    
    def get_size(self):
        self.size = (self.width, self.hight)
        return self.size

    def get_position(self):
        self.position = (self.ux, self.ly)
        return self.position
        
class Board(BaseElement):
    def __init__(self, width, hight):
        self.width = width
        self.hight = hight
        self.image = Image.new('RGBA', (self.width, self.hight), (255, 255, 255, 0))
        self.elements = []
        
    def render(self):
        for i in self.elements:
            i.ux = self.width * i.box[0]
            i.ly = self.hight * i.box[1]
            i.dx = self.width * i.box[2]
            i.ry = self.hight * i.box[3]
            i.hight = i.dx - i.ux
            i.width = i.ry - i.ly
            i.position = (i.ux, i.ly)
            image = i.render()
            self.image.paste(image, i.get_position())
    
    def add_element(self, element:BaseElement):
        self.elements.append(element)


class Container(BaseElement):
    def __init__(self, box:Union[Iterable[int],Iterable[float]] = (0, 0, 0, 0)):
        super().__init__(box)
        self.elements:List[BaseElement] = []

    def render(self,size:Tuple[int, int] = (100, 100)):
        if not self.width and self.hight:
            self.width = size[0]
            self.hight = size[1]
        if not self.image:
            self.image = Image.new('RGBA', (self.width, self.hight), (255, 255, 255, 0))
        for i in self.elements:
            image = i.render()
            self.image.paste(image, i.get_position())

class Element(BaseElement):
    



# class BaseContainer(abc.ABC):
#     def __init__(self, width:int, height:int):
#         self.width = width
#         self.height = height
#         self.image = Image.new('RGBA', (self.width, self.height), (255, 255, 255, 0))
        
#     @abc.abstractmethod
#     def render(self):
#         raise NotImplementedError
    
#     def set_image(self,image):
#         self.image = image
        
# class Elements():
#     def __init__(self, width:int, height:int):
#         self.width = width
#         self.height = height
#         self.image = Image.new('RGBA', (self.width, self.height), (255, 255, 255, 0))

#     def render(self):
#         return self.image
    
# class Container(BaseContainer):
#     def __init__(self, width:int, height:int,elements:List[Union['Container',Elements]] = []):
#         super().__init__(width, height)
#         self.elements = elements

#     def render(self):
#         for i in self.elements:
#             image = i.render()
#             self.image.paste(image, i.position)
#         return self.image
    