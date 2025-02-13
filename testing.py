import pygame, laser
w=pygame.display.set_mode([500,500])

thelaser=laser.Laser()

thelaser.updateLaser(100,100,500,500)
thelaser.laserPoints= thelaser.getLaserPoints(6)
thelaser2=laser.Laser()

thelaser2.updateLaser(100,100,500,500)
thelaser2.laserPoints= thelaser.getLaserPoints(6)

running=True
c=pygame.time.Clock()

while running:
    for event in pygame.event.get():
        if event.type==pygame.QUIT:
            running=False
        if event.type==pygame.KEYDOWN:
            thelaser.laserPoints=thelaser.getLaserPoints(6)
            thelaser2.laserPoints=thelaser2.getLaserPoints(6)

    x,y=pygame.mouse.get_pos()
    thelaser.updateLaser(100,100,x,y)
    thelaser2.updateLaser(100,100,x,y)


    thelaser.tick(16)
    thelaser2.tick(16)
    w.fill((0,0,0))
    thelaser.draw(w,0)
    thelaser2.draw(w,0)

    c.tick(60)
    pygame.display.flip()