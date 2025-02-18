# imports
import pygame,world, random,UI

class Game:
    def __init__(self,window,FPS=60,developingMode=False):

        self.window = window

        # constants
        self.FPS = FPS
        self.DEFAULT_ZOOMS = [0.1,2]
        self.WORLD_WIDTH = 3000
        self.WORLD_HEIGHT = 10000

        # set up variables
        self.mode = "play"

        self.developingMode= developingMode
        
    
    def coordsWindowToWorld(self,coords:list[int]):
        return self.camX+coords[0]/self.zoom,self.camY+coords[1]/self.zoom

    def getWorldCenteredCam(self):
        return self.getCenteredCam((self.WORLD_WIDTH/2,self.WORLD_HEIGHT/2))
    
    def getCenteredCam(self, center):
        return center[0]-self.window.get_width()/self.zoom/2,center[1]-self.window.get_height()/self.zoom/2

    def getWindowCenterWorldCoords(self):
        return self.coordsWindowToWorld([self.window.get_width()/2,self.window.get_height()/2])

    def setZoom(self, newZoom, zoomCenter):
        zoomRatio = self.zoom/newZoom
        self.camX-=(zoomCenter[0]-self.camX)*(zoomRatio-1)
        self.camY-=(zoomCenter[1]-self.camY)*(zoomRatio-1)
        self.zoom=newZoom
    
    def updateCamPos(self, FPS, zoom, playerX,playerY,playerXSpeed,playerYSpeed):
        frameLength=1000/FPS
        self.camOffsetX+=2*playerXSpeed*frameLength
        self.camOffsetY+=2*playerYSpeed*frameLength
        self.camOffsetX=min(max(self.camOffsetX,self.window.get_width()/zoom*1/6),self.window.get_width()/zoom*(-1/6))
        self.camOffsetY=min(max(self.camOffsetY,self.window.get_height()/zoom*1/6),self.window.get_height()/zoom*(-1/6))
        self.camOffsetX,self.camOffsetY=0,0
        self.camX += (self.camOffsetX+playerX-self.camX-self.window.get_width()/zoom/2)*frameLength/200
        self.camY += (self.camOffsetY+max(50,playerY)-self.camY-self.window.get_height()/zoom/2)*frameLength/200


    def run(self):
        
        #self.window = pygame.display.set_mode([self.window.get_width(),self.window.get_height()])
        #self.window.get_width(),self.window.get_height()=self.window.get_size()
        
        self.chargeDisplay=UI.ChargeDisplay(self.WORLD_HEIGHT)
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

        self.shake=0

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
                    print("quit")
                    running=False
                    return
                    
                # TEMPORARY for testing
                if event.type==pygame.MOUSEBUTTONDOWN:
                    self.events["mouseDown"]=True
                    self.keysDown["mouse"]=True
                    x,y= self.coordsWindowToWorld((mouseX,mouseY))
                    
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
                            case pygame.K_t:
                                x,y= self.coordsWindowToWorld((mouseX,mouseY))

                                self.gameWorld.player.x,self.gameWorld.player.y=x,y
                                self.gameWorld.player.updateRect()
                
                if event.type==pygame.KEYUP:
                    if event.key in self.keysDown:
                        self.keysDown[event.key]=False
            
            startCharge=self.gameWorld.player.charge
            self.gameWorld.tick(practicalFPS,self.window,[self.camX,self.camY,self.zoom],self.coordsWindowToWorld((mouseX,mouseY)),self.keysDown,self.events)
            self.chargeDisplay.update(practicalFPS,self.gameWorld.player.color,startCharge,self.gameWorld.player.charge,self.gameWorld.player.y)

            self.updateCamPos(practicalFPS,self.zoom,self.gameWorld.player.x,self.gameWorld.player.y,self.gameWorld.player.xSpeed,self.gameWorld.player.ySpeed)

            # clear window
            self.window.fill((0,0,0))
            
            for lase in self.gameWorld.player.laser:
                if lase.damageFrame:
                    self.shake=self.gameWorld.player.laserPower/20
                else:
                    self.shake+=self.gameWorld.player.laserPower/300
                    #self.shake+=0.1
            self.shake*=0.9

            # display world layer
            self.window.blit(self.gameWorld.getSurface(self.window,[self.camX+(2*random.random()-1)*self.shake,self.camY+(2*random.random()-1)*self.shake,self.zoom],hitboxes=self.visibleHitboxes,kindVisibility=self.kindVisibility),(0,0))

            # display UI stuff
            self.chargeDisplay.draw(self.window)

            # update window
            pygame.display.flip()

            # tick game
            self.clock.tick(self.FPS)
            practicalFPS= max(1,round(1000/(pygame.time.get_ticks()-previousTime)))
            if random.randint(1,10)==1:
                print("fps:", practicalFPS)
            previousTime=pygame.time.get_ticks()
