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
    passedThresholds:dict

base=LaserAttributes(10,0.8,0.15,20,500,1,20,0.3,1,20,20,0.5,1.5,0.5,{})
maxWhite=LaserAttributes(25,1.2,0.25,40,300,1,50,0.3,1,30,30,0.5,2,0.5,{})
maxBlue=LaserAttributes(30,3,0.8,35,400,1,20,0.3,1,20,50,0.5,3,0.5,{})
maxRed=LaserAttributes(5,5,0.15,60,500,0.2,20,1,1,50,20,0.8,1.5,1,{})

abilityThresholds={
    "white":200/500,
    "blue":200/500,
    "red":200/500
}

boostThresholds={
    "white":[180/500,400/500],
    "blue":[120/500],
    "red":[120/500,400/500]
}

def setLaserAttributes(attributes:LaserAttributes, charges, filter, maxCharge=500):

    for color in attributes.passedThresholds:
        nPassed=0
        charge=charges[color]/maxCharge
        for threshold in boostThresholds[color]:
            if threshold<=charge:
                nPassed+=1
        attributes.passedThresholds[color]=(nPassed,attributes.passedThresholds[color][1] or charge>abilityThresholds[color])

    w,b,r = charges["white"]/maxCharge,charges["blue"]/maxCharge,charges["red"]/maxCharge
    
    for field in fields(attributes):
        
        fieldName=field.name

        if fieldName != "passedThresholds":
            baseAtt=getattr(base, fieldName)
            whiteAttr=getattr(maxWhite, fieldName)
            blueAttr=getattr(maxBlue, fieldName)
            redAttr=getattr(maxRed, fieldName)
            
            value=baseAtt+w*(whiteAttr-baseAtt)+b*(blueAttr-baseAtt)+r*(redAttr-baseAtt)
            if fieldName=="distance":
                value=int(value)

            setattr(attributes,fieldName,value)
    
    match filter:
        case "white":
            if attributes.passedThresholds[filter][0]>=2:
                attributes.rampRate+=1
        case "blue":
            if attributes.passedThresholds[filter][0]>=1:
                attributes.firstHitKBMultiplier*=1.5
        case "red":
            if attributes.passedThresholds[filter][0]>=1:
                attributes.DMGRange+=30


    return attributes

def getLaserDMG(attributes:LaserAttributes, firstHit:bool, ramps:int):
    if firstHit:
        return attributes.baseDMG*attributes.firstHitDMGMultiplier
    else:
        out=attributes.baseDMG*(1+attributes.rampRate*min(attributes.rampMax,ramps))
        return out
    
def getLaserKB(attributes:LaserAttributes, firstHit:bool, ramps:int):
    if firstHit:
        return attributes.baseKB*attributes.firstHitKBMultiplier
    else:
        out=attributes.baseKB
        return out

def getLaserEXPL(attributes:LaserAttributes, firstHit:bool, ramps:int):
    if firstHit:
        return attributes.baseXPL*attributes.firstHitXPLMultiplier
    else:
        out=attributes.baseXPL
        return out
    