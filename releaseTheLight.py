# imports
import pygame, random
pygame.init()

class Game:
    def __init__(self,FPS=60,WINDOW_WIDTH=1200,WINDOW_HEIGHT=700,developingMode=False):

        # constants
        self.FPS = FPS
        self.DEFAULT_ZOOMS = [0.1,2]
        self.WORLD_WIDTH = 3000
        self.WORLD_HEIGHT = 5000
        self.WINDOW_WIDTH = WINDOW_WIDTH
        self.WINDOW_HEIGHT=WINDOW_HEIGHT

        # set up variables
        self.mode = "play"

        self.developingMode= developingMode
    
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
    
    def updateCamPos(self, FPS, zoom, playerX,playerY,playerXSpeed,playerYSpeed):
        frameLength=1000/FPS
        self.camOffsetX+=2*playerXSpeed*frameLength
        self.camOffsetY+=2*playerYSpeed*frameLength
        self.camOffsetX=min(max(self.camOffsetX,self.WINDOW_WIDTH/zoom*1/6),self.WINDOW_WIDTH/zoom*(-1/6))
        self.camOffsetY=min(max(self.camOffsetY,self.WINDOW_HEIGHT/zoom*1/6),self.WINDOW_HEIGHT/zoom*(-1/6))
        self.camOffsetX,self.camOffsetY=0,0
        self.camX += (self.camOffsetX+playerX-self.camX-self.WINDOW_WIDTH/zoom/2)*frameLength/100
        self.camY += (self.camOffsetY+playerY-self.camY-self.WINDOW_HEIGHT/zoom/2)*frameLength/100
        self.screenshakeX=0
        self.screenshakeY=0

    def run(self):
        
        self.window = pygame.display.set_mode([self.WINDOW_WIDTH,self.WINDOW_HEIGHT])
        import world
        self.gameWorld = world.World(self.WORLD_WIDTH,self.WORLD_HEIGHT,defaultZooms=self.DEFAULT_ZOOMS)
        self.clock = pygame.time.Clock()
        self.keysDown = {pygame.K_w:False,
                         pygame.K_a:False,
                         pygame.K_d:False,
                         "mouse":False}
        self.events = {"mouseDown":False,"mouseUp":False}

        self.zoom=self.DEFAULT_ZOOMS[1]
        self.camX,self.camY=self.getWorldCenteredCam()
        self.camOffsetX,self.camOffsetY=0,0

        previousTime=pygame.time.get_ticks()
        running = True
        self.kindVisibility=False
        practicalFPS=self.FPS
        self.visibleHitboxes=False

        while running:

            # get mouse pos
            mouseX,mouseY=pygame.mouse.get_pos()

            # player inputs
            self.events = {"mouseDown":False,"mouseUp":False}
            for event in pygame.event.get():

                # close game
                if event.type==pygame.QUIT:
                    running=False
                    return
                    
                # TEMPORARY for testing
                if event.type==pygame.MOUSEBUTTONDOWN:
                    self.events["mouseDown"]=True
                    self.keysDown["mouse"]=True
                    x,y= self.coordsWindowToWorld((mouseX,mouseY))

                    self.gameWorld.player.x,self.gameWorld.player.y=x,y
                    self.gameWorld.player.updateRect()
                    
                    #self.gameWorld.terrain.generateSkinnyCave(x,y,50)

                    #self.gameWorld.terrain.generateNest(x,y,"White",100)
                if event.type==pygame.MOUSEBUTTONUP:
                    self.keysDown["mouse"]=False
                    self.events["mouseUp"]=True

                if event.type==pygame.KEYDOWN:
                    if event.key in self.keysDown:
                        self.keysDown[event.key]=True
                    
                    # TEMPORARY - zoom in/out
                    if self.developingMode:
                        match event.key:
                            case pygame.K_z:
                                if self.zoom==0.1:
                                    self.setZoom(2,self.coordsWindowToWorld((mouseX,mouseY)))
                                else:
                                    self.setZoom(0.1,self.coordsWindowToWorld((mouseX,mouseY)))
                            case pygame.K_0:
                                self.kindVisibility= not self.kindVisibility
                            case pygame.K_h:
                                self.visibleHitboxes=not self.visibleHitboxes
                
                if event.type==pygame.KEYUP:
                    if event.key in self.keysDown:
                        self.keysDown[event.key]=False
            
            self.gameWorld.tick(practicalFPS,self.window,[self.camX,self.camY,self.zoom],self.coordsWindowToWorld((mouseX,mouseY)),self.keysDown,self.events)

            self.updateCamPos(practicalFPS,self.zoom,self.gameWorld.player.x,self.gameWorld.player.y,self.gameWorld.player.xSpeed,self.gameWorld.player.ySpeed)

            # clear window
            self.window.fill((0,0,0))

            # display terrain layer
            self.window.blit(self.gameWorld.getSurface(self.window,[self.camX,self.camY,self.zoom],hitboxes=self.visibleHitboxes,kindVisibility=self.kindVisibility),(0,0))

            # update window
            pygame.display.flip()

            # tick game
            self.clock.tick(self.FPS)
            practicalFPS= max(1,round(1000/(pygame.time.get_ticks()-previousTime)))
            print("fps:", practicalFPS)
            previousTime=pygame.time.get_ticks()
