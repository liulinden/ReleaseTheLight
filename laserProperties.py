from dataclasses import dataclass, fields

@dataclass
class LaserAttributes:
    distance:int
    baseDMG:float
    baseKB:float
    baseXPL:float
    cooldown:float
    rampRate:float
    rampMax:float
    areaDMGFalloff:float
    areaKBFalloff:float
    DMGRange:int
    KBRange:int
    firstHitDMGMultiplier:float
    firstHitKBMultiplier:float
    firstHitXPLMultiplier:float

base=LaserAttributes(10,0.8,0.15,20,500,1,20,0.3,1,20,20,0.5,1.5,0.5)
maxWhite=LaserAttributes(25,2,0.3,40,300,1,30,0.3,1,30,30,0.5,2,0.5)
maxBlue=LaserAttributes(30,3,0.8,35,400,1,20,0.3,1,20,50,0.5,3,0.5)
maxRed=LaserAttributes(5,5,0.15,60,500,0.2,20,1,1,50,20,0.8,1.5,0.8)

def setLaserAttributes(attributes:LaserAttributes, charges, maxCharge=500):

    w,b,r = charges["white"]/maxCharge,charges["blue"]/maxCharge,charges["red"]/maxCharge
    
    for field in fields(attributes):
        
        fieldName=field.name

        baseAtt=getattr(base, fieldName)
        whiteAttr=getattr(maxWhite, fieldName)
        blueAttr=getattr(maxBlue, fieldName)
        redAttr=getattr(maxRed, fieldName)
        
        value=baseAtt+w*(whiteAttr-baseAtt)+b*(blueAttr-baseAtt)+r*(redAttr-baseAtt)
        if fieldName=="distance":
            value=int(value)

        setattr(attributes,fieldName,value)

    return attributes

def getLaserDMG(attributes:LaserAttributes, firstHit:bool, ramps:int):
    if firstHit:
        return attributes.baseDMG*attributes.firstHitDMGMultiplier
    else:
        return attributes.baseDMG*(1+attributes.rampRate*min(attributes.rampMax,ramps))
    
def getLaserKB(attributes:LaserAttributes, firstHit:bool):
    if firstHit:
        return attributes.baseKB*attributes.firstHitKBMultiplier
    else:
        return attributes.baseKB

def getLaserEXPL(attributes:LaserAttributes, firstHit:bool):
    if firstHit:
        return attributes.baseXPL*attributes.firstHitXPLMultiplier
    else:
        return attributes.baseXPL
    