# imports
import world, pygame, random

#load images
light=pygame.transform.scale(pygame.image.load(".Light.png"),(600,600))

class Game:
    def __init__(self,FPS=60,WINDOW_WIDTH=1000,WINDOW_HEIGHT=700):

        # constants
        self.FPS = FPS
        self.DEFAULT_ZOOMS = [0.1,2]
        self.WORLD_WIDTH = 6000
        self.WORLD_HEIGHT = 4000
        self.WINDOW_WIDTH = WINDOW_WIDTH
        self.WINDOW_HEIGHT=WINDOW_HEIGHT

        # set up variables
        self.mode = "play"
    
    def coordsWindowToWorld(self,coords:list[int]):
        return self.camX+coords[0]/self.zoom,self.camY+coords[1]/self.zoom

    def getWorldCenteredCam(self):
        return self.getCenteredCam((self.WORLD_WIDTH/2,self.WORLD_HEIGHT/2))
    
    def getCenteredCam(self, center):
        return center[0]-self.WINDOW_WIDTH/self.zoom/2,center[1]-self.WINDOW_HEIGHT/self.zoom/2

    def getWindowCenterWorldCoords(self):
        return self.coordsWindowToWorld([self.WINDOW_WIDTH/2,self.WINDOW_HEIGHT/2])

    def setZoom(self, newZoom, zoomCenter):
        zoomRatio = self.zoom/newZoom
        self.camX-=(zoomCenter[0]-self.camX)*(zoomRatio-1)
        self.camY-=(zoomCenter[1]-self.camY)*(zoomRatio-1)
        self.zoom=newZoom


    def run(self):

        self.window = pygame.display.set_mode([self.WINDOW_WIDTH,self.WINDOW_HEIGHT])
        self.gameWorld = world.World(self.WORLD_WIDTH,self.WORLD_HEIGHT,defaultZooms=self.DEFAULT_ZOOMS)
        self.clock = pygame.time.Clock()

        self.zoom=self.DEFAULT_ZOOMS[0]
        self.camX,self.camY=self.getWorldCenteredCam()

        previousTime=pygame.time.get_ticks()
        running = True
        while running:

            # get mouse pos
            mouseX,mouseY=pygame.mouse.get_pos()

            # player inputs
            for event in pygame.event.get():

                # close game
                if event.type==pygame.QUIT:
                    running=False
                    return
                    
                # TEMPORARY - create new cave
                if event.type==pygame.MOUSEBUTTONDOWN:
                    x,y= self.coordsWindowToWorld((mouseX,mouseY))
                    self.gameWorld.terrain.generateSkinnyCave(x,y,50)
                
                # TEMPORARY - zoom in/out
                if event.type==pygame.KEYDOWN:
                    if event.key == pygame.K_z:
                        if self.zoom==0.1:
                            self.setZoom(2,self.coordsWindowToWorld((mouseX,mouseY)))
                        else:
                            self.setZoom(0.1,self.coordsWindowToWorld((mouseX,mouseY)))
            self.camX+=1

            self.gameWorld.tick(self.FPS,self.window,[self.camX,self.camY,self.zoom])
            # clear window
            self.window.fill((0,0,0))

            # TEMPORARY - display light at mouse position
            #window.blit(light,(x-300,y-300))
            #window.blit(light,(x-300,y-300))

            # display terrain layer
            self.window.blit(self.gameWorld.getSurface(self.window,[self.camX,self.camY,self.zoom]),(0,0))

            # update window
            pygame.display.flip()

            # tick game
            self.clock.tick(self.FPS)
            print("fps:", round(1000/(pygame.time.get_ticks()-previousTime)))
            previousTime=pygame.time.get_ticks()
