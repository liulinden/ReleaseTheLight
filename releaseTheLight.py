# imports
import pygame,world, random,UI

class Game:
    def __init__(self,window,FPS=60,fullWorld=True,developingMode=False):

        self.window = window
        self.window_width,self.window_height=window.get_size()

        # constants
        self.FPS = FPS
        if developingMode:
            self.DEFAULT_ZOOMS = [0.1,1,1.5]
        else:
            self.DEFAULT_ZOOMS = [1,1.5]
        #self.HITBOX_ZOOM=0.2 -- add later
        self.WORLD_WIDTH = 4000
        self.WORLD_HEIGHT = 20000
        if not fullWorld:
            self.WORLD_HEIGHT=8000
        #high temporarily

        self.offset_x=0
        self.offset_y=0

        # set up variables
        self.mode = "play"

        self.developingMode= developingMode
        
    
    def coordsWindowToWorld(self,coords:list[int]):
        return self.camX+(coords[0]-self.offset_x)/self.zoom,self.camY+(coords[1]-self.offset_y)/self.zoom

    def getWorldCenteredCam(self):
        return self.getCenteredCam((self.WORLD_WIDTH/2,self.WORLD_HEIGHT/2))
    
    def getCenteredCam(self, center):
        return center[0]-self.window_width/self.zoom/2,center[1]-self.window_height/self.zoom/2

    def getWindowCenterWorldCoords(self):
        return self.coordsWindowToWorld([self.window_width/2,self.window_height/2])

    def setZoom(self, newZoom, zoomCenter):
        zoomRatio = self.zoom/newZoom
        self.camX-=(zoomCenter[0]-self.camX)*(zoomRatio-1)
        self.camY-=(zoomCenter[1]-self.camY)*(zoomRatio-1)
        self.zoom=newZoom
    
    def updateCamPos(self, FPS, zoom, playerX,playerY,playerXSpeed,playerYSpeed):
        frameLength=1000/FPS
        self.camOffsetX+=2*playerXSpeed*frameLength
        self.camOffsetY+=2*playerYSpeed*frameLength
        self.camOffsetX=min(max(self.camOffsetX,self.window_width/zoom*1/6),self.window_width/zoom*(-1/6))
        self.camOffsetY=min(max(self.camOffsetY,self.window_height/zoom*1/6),self.window_height/zoom*(-1/6))
        self.camOffsetX,self.camOffsetY=0,0
        goalX=max(self.window_width/zoom/2,min(self.WORLD_WIDTH-self.window_width/zoom/2,playerX))
        if self.window_width/zoom/2 >self.WORLD_WIDTH-self.window_width/zoom/2:
            goalX=playerX
        goalY=max(-100,min(self.WORLD_HEIGHT-100,playerY))
        self.camX += (self.camOffsetX+goalX-self.camX-self.window_width/zoom/2)*frameLength/200
        self.camY += (self.camOffsetY+goalY-self.camY-self.window_height/zoom/2)*frameLength/200


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

        self.zoom=self.DEFAULT_ZOOMS[len(self.DEFAULT_ZOOMS)-1]
        self.defaultCamCoords=self.getWorldCenteredCam()[0],-100
        self.camX,self.camY=self.defaultCamCoords
        self.camOffsetX,self.camOffsetY=0,0

        self.shake=0

        previousTime=pygame.time.get_ticks()
        running = True
        self.kindVisibility=False
        practicalFPS=self.FPS
        self.visibleHitboxes=False
        self.loadingDebug=False

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
                        if event.key== pygame.K_z:
                            newZoom=0
                            if self.DEFAULT_ZOOMS.index(self.zoom)==len(self.DEFAULT_ZOOMS)-1:
                                newZoom=self.DEFAULT_ZOOMS[0]
                            else:
                                newZoom=self.DEFAULT_ZOOMS[self.DEFAULT_ZOOMS.index(self.zoom)+1]
                            self.setZoom(newZoom,(self.gameWorld.player.x,self.gameWorld.player.y))
                        elif event.key== pygame.K_0:
                            self.kindVisibility= not self.kindVisibility
                        elif event.key== pygame.K_h:
                            self.visibleHitboxes=not self.visibleHitboxes
                        elif event.key== pygame.K_t:
                            x,y= self.coordsWindowToWorld((mouseX,mouseY))

                            self.gameWorld.player.x,self.gameWorld.player.y=x,y
                            self.gameWorld.player.updateRect()
                        elif event.key== pygame.K_l:
                            if not self.loadingDebug:
                                self.window_width,self.window_height=300,200
                                self.offset_x=(self.window.get_width()-self.window_width)/2
                                self.offset_y=(self.window.get_height()-self.window_height)/2
                            else:
                                self.window_width,self.window_height=self.window.get_size()
                                self.offset_x=0
                                self.offset_y=0
                            self.loadingDebug=not self.loadingDebug
                
                if event.type==pygame.KEYUP:
                    if event.key in self.keysDown:
                        self.keysDown[event.key]=False
            
            if self.gameWorld.tick(practicalFPS,(self.window_width,self.window_height),[self.camX,self.camY,self.zoom],self.coordsWindowToWorld((mouseX,mouseY)),self.keysDown,self.events):
                self.camX,self.camY=self.defaultCamCoords
                self.gameWorld.healNests()
                self.gameWorld.removeEnemies()

            self.chargeDisplay.update(practicalFPS,self.gameWorld.player.color,self.gameWorld.player.charge,self.gameWorld.player.y)

            self.updateCamPos(practicalFPS,self.zoom,self.gameWorld.player.x,self.gameWorld.player.y,self.gameWorld.player.xSpeed,self.gameWorld.player.ySpeed)
            #world wrapping
            #if self.gameWorld.player.x>self.WORLD_WIDTH:
            #    self.gameWorld.player.x-=self.WORLD_WIDTH
            #    self.camX-=self.WORLD_WIDTH
            #elif self.gameWorld.player.x<0:
            #    self.gameWorld.player.x+=self.WORLD_WIDTH
            #    self.camX+=self.WORLD_WIDTH

            # clear window
            self.window.fill((255,255,255))
            
            for lase in self.gameWorld.player.laser:
                if lase.damageFrame:
                    self.shake=self.gameWorld.player.laserPower/12
                else:
                    self.shake+=self.gameWorld.player.laserPower/500
                    #self.shake+=0.1
            self.shake*=0.9

            # display world layer
            frame=[self.camX+(2*random.random()-1)*self.shake,self.camY+(2*random.random()-1)*self.shake,self.zoom]
            #self.window.blit(self.gameWorld.getSurface((self.window_width,self.window_height),frame,hitboxes=self.visibleHitboxes,kindVisibility=self.kindVisibility),(0,0))

            self.window.blit(self.gameWorld.getSurface((self.window_width,self.window_height),frame,hitboxes=self.visibleHitboxes,kindVisibility=self.kindVisibility,real_window_size=self.window.get_size(),offset_x=self.offset_x,offset_y=self.offset_y),(0,0))

            # display UI stuff
            self.chargeDisplay.draw(self.window)

            if self.loadingDebug:
                pygame.draw.rect(self.window,(0,255,0),pygame.Rect(self.offset_x,self.offset_y,self.window_width,self.window_height),1)

            # update window
            pygame.display.flip()

            # tick game
            self.clock.tick(self.FPS)
            practicalFPS= max(1,round(1000/(pygame.time.get_ticks()-previousTime)))
            if random.randint(1,10)==1:
                print("fps:", practicalFPS)
            practicalFPS=max(30,practicalFPS)
            previousTime=pygame.time.get_ticks()
