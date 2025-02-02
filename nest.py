import pygame, random

def loadImages(imgs):
    out = []
    for img in imgs:
        out.append(pygame.image.load(img))
    return out

whiteVariants = [loadImages([])]
redVariants = [loadImages([])]
blueVariants = [loadImages([])]
sun=[loadImages([])]


class Nest:
    def __init__(self,x,y,nestType):
        self.x=x
        self.y=y
        self.nestType=nestType
        
        variants=[]
        match self.nestType:
            case "white":
                variants=whiteVariants
            case "red":
                variants=redVariants
            case "blue":
                variants=blueVariants
            case "sun":
                variants=sun
        
        self.nestIMGs = variants[random.randint(0,len(variants)-1)]