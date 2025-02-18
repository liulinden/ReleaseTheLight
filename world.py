# imports
import pygame, random, terrain, decoration, aplayer,lighting,math

def distance(coord1:int,coord2:int):
    x1,y1=coord1
    x2,y2=coord2
    return math.sqrt((x1-x2)**2+(y1-y2)**2)

# load images
airIMGs=[]
for i in range(5):
    airIMGs.append(pygame.image.load(".AirPocket"+str(i+1)+".png").convert_alpha())

# overall game world class
class World:

    # set up and create world
    def __init__(self, worldWidth, worldHeight, defaultZooms=[0.1,2]):

        # set up world data
        self.terrain = terrain.Terrain(worldWidth,worldHeight,defaultZooms=defaultZooms)
        self.decorations=[]
        self.worldWidth=worldWidth
        self.worldHeight=worldHeight
        self.defaultZooms = defaultZooms
        self.player= aplayer.Player(defaultZooms,worldWidth/2,-200)
        self.light=lighting.Lighting(defaultZooms=defaultZooms)

        # procedural generation
        self.generateWorld()
    
    # generate caves/nests/decorations
    def generateWorld(self):
        self.terrain.generate()
    
    # create an air pocket at x, y with specified radius
    def addAirPocket(self, x, y, radius):
        self.terrain.addAirPocket(x,y,radius)
    
    #perform frame actions
    def tick(self,FPS,window,frame, mousePos,keysDown,events):
        left,top,zoom=frame
        frameLength=1000/FPS

        self.terrain.newKnockbackCircles=[]
        self.terrain.newPlayerDamageCircles=[]

        #enemy ticking

        #player ticking
        self.player.tick(frameLength,self.terrain, mousePos,keysDown,events)

        #change camx camy
        if random.randint(1,math.ceil(FPS/10))==1:
            self.light.addMistParticle(self.player.x,self.player.y,color=self.player.color)
        for lase in self.player.laser:
            if random.randint(1,math.ceil(FPS/max(1,lase.length)*50))==1:
                mistPos= random.random()
                self.light.addMistParticle(lase.startX+mistPos*lase.length*math.cos(lase.angle),lase.startY+mistPos*lase.length*math.sin(lase.angle),color=self.player.color)

        w_width,w_height=window.get_size()
        x,y,r=left+w_width/zoom/2,top+w_height/zoom/2,distance((0,0),(w_width,w_height))/2/zoom
        for nest in self.terrain.nests:
            nest.updateVisuals(frameLength)
            nest.applyDamageFromCircles(self.terrain.playerDamageCircles)
            """
            if nest.stage!=nest.maxStage:
                d=distance((self.x,self.y),(nest.x,nest.y))
                if d<1000 and random.randint(1,int(d/2)):
                    nest.addEnemy()"""
            if random.randint(1,math.ceil(FPS/6))==1 and nest.close(x,y,r) and nest.stage==nest.maxStage:
                self.light.addMistParticle(nest.x,nest.y,color=nest.color)
        
        self.light.tickEffects(frameLength)

        self.terrain.knockbackCircles=self.terrain.newKnockbackCircles
        self.terrain.playerDamageCircles=self.terrain.newPlayerDamageCircles
        #draw
        
        ...
    
    # return world layer
    def getSurface(self,window,frame,hitboxes=False,kindVisibility=False):

        # set up layer
        layer=pygame.Surface(window.get_size())
        if kindVisibility:
            layer.fill((200,200,200,0))
        else:
            layer.fill((0,0,0,0))

        # add lighting layer
        self.light.drawGradient(layer,frame,self.player.color,self.player.x,self.player.y)
        self.light.drawEffects(layer,frame)

        
        #add enemies layer

        # add player layer
        self.player.draw(layer, frame,hitboxes=hitboxes)

        # add nests layer
        self.terrain.drawNests(layer,frame, hitboxes=hitboxes)

        # add terrain layer
        layer.blit(self.terrain.getTerrainLayer(window,frame,hitboxes=hitboxes),(0,0),special_flags=pygame.BLEND_RGBA_SUB)

        # add parralax

        return layer