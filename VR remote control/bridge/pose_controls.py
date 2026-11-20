"""Quaternion XYZW helpers and relative controller orientation/gripper clutch."""
import math

IDENTITY = [0., 0., 0., 1.]

def normalize(q):
    n = math.sqrt(sum(x*x for x in q))
    if n < 1e-8 or not math.isfinite(n): raise ValueError('无效手柄旋转')
    return [x/n for x in q]

def mul(a,b):
    x,y,z,w=a; X,Y,Z,W=b
    return normalize([w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z])

def inv(q):
    x,y,z,w=normalize(q)
    return [-x,-y,-z,w]

def angle(a,b):
    dot=abs(sum(x*y for x,y in zip(normalize(a),normalize(b))))
    return 2*math.acos(min(1.,dot))

def toward(a,b,max_angle):
    a,b=normalize(a),normalize(b)
    if sum(x*y for x,y in zip(a,b))<0:b=[-x for x in b]
    theta=angle(a,b)
    if theta<=max_angle or theta<1e-8:return b
    t=max_angle/theta
    h=theta/2
    return normalize([(math.sin((1-t)*h)*x+math.sin(t*h)*y)/math.sin(h) for x,y in zip(a,b)])

def robot_delta(current,anchor):
    # R_robot = M R_unity M^T; M(x,y,z)=(z,-x,y), det(M)=-1.
    # Quaternion vector is axial: det(M)*M*v, not M*v.
    x,y,z,w=mul(current,inv(anchor))
    return [-z,x,-y,w]

class PoseControls:
    def __init__(self):
        self.clutch=None
        self.anchor_rotation=IDENTITY
        self.anchor_target=IDENTITY
        self.anchor_trigger=0.
        self.anchor_gripper=0.
        self.last_time=None
        self.last_hand=None

    def goals(self, hand, clutch, rotation, gripper, now, orientation_enabled, gripper_enabled):
        if clutch!=self.clutch:
            self.clutch=clutch
            self.anchor_rotation=normalize(hand['rotation'])
            self.anchor_target=list(rotation)
            self.anchor_trigger=hand['trigger']
            self.anchor_gripper=gripper
            self.last_time=now
            self.last_hand=normalize(hand['rotation'])
        dt=max(0.,min(.1,now-self.last_time));self.last_time=now
        goal=list(rotation)
        if orientation_enabled:
            delta=robot_delta(hand['rotation'],self.anchor_rotation)
            if angle(self.last_hand,hand['rotation'])>math.radians(100):
                raise ValueError('手柄姿态变化过大，请松开握键后重新启用')
            goal=toward(rotation,mul(delta,self.anchor_target),math.radians(90)*dt)
        self.last_hand=normalize(hand['rotation'])
        opening=gripper
        if gripper_enabled:
            desired=max(0.,min(100.,self.anchor_gripper-100*(hand['trigger']-self.anchor_trigger)))
            opening=gripper+max(-50*dt,min(50*dt,desired-gripper))
        return goal,opening
