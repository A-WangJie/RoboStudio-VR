using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.Controls;
using UnityEngine.InputSystem.XR;
using UnityEngine.XR;
using InputDevice = UnityEngine.InputSystem.InputDevice;

namespace RoboStudioVR {
// Always resolve live devices, including controllers that appear after app startup.
// UI and telemetry use the same controller; aim pose and grip pose stay distinct.
public static class ControllerInput {
    public struct Sample {
        public bool connected, tracked, aimTracked, primary, secondary;
        public Vector3 position, aimPosition;
        public Quaternion rotation, aimRotation;
        public Vector2 stick;
        public float trigger, grip;
        public int deviceId;
        public QuestTelemetrySender.Hand Telemetry(bool focused) {
            bool valid=focused && tracked;
            return new QuestTelemetrySender.Hand {
                connected=connected, tracked=valid,
                position=valid?new[]{position.x,position.y,position.z}:new float[3],
                rotation=valid?new[]{rotation.x,rotation.y,rotation.z,rotation.w}:new[]{0f,0f,0f,1f},
                stick=focused?new[]{stick.x,stick.y}:new float[2],
                trigger=focused?trigger:0, grip=focused?grip:0,
                primary=focused && primary, secondary=focused && secondary
            };
        }
    }
    public static Sample Read(XRNode side) {
        var best=new Sample {rotation=Quaternion.identity,aimRotation=Quaternion.identity};
        int bestScore=-1;
        var usage=side==XRNode.LeftHand?UnityEngine.InputSystem.CommonUsages.LeftHand:UnityEngine.InputSystem.CommonUsages.RightHand;
        foreach(var device in InputSystem.devices) {
            if(!(device is XRController) || !device.added || !device.enabled)continue;
            bool match=false;
            foreach(var tag in device.usages)if(tag==usage){match=true;break;}
            if(!match)continue;
            // Physical controller profiles expose both squeeze and trigger axes.
            var trigger=device.TryGetChildControl<AxisControl>("trigger");
            var grip=device.TryGetChildControl<AxisControl>("grip");
            if(trigger==null || grip==null)continue;
            var sample=new Sample {connected=true,deviceId=device.deviceId};
            sample.tracked=Pose(device.TryGetChildControl<InputControl>("devicePose")??device,out sample.position,out sample.rotation);
            sample.aimTracked=Pose(device.TryGetChildControl<InputControl>("pointer"),out sample.aimPosition,out sample.aimRotation);
            sample.trigger=Axis(trigger);sample.grip=Axis(grip);
            sample.primary=device.TryGetChildControl<ButtonControl>("primaryButton")?.isPressed??false;
            sample.secondary=device.TryGetChildControl<ButtonControl>("secondaryButton")?.isPressed??false;
            sample.stick=device.TryGetChildControl<Vector2Control>("thumbstick")?.ReadValue()??Vector2.zero;
            if(!Finite(sample.stick.x)||!Finite(sample.stick.y))sample.stick=Vector2.zero;
            int score=(sample.tracked?4:0)+(sample.aimTracked?2:0);
            if(score>=bestScore){bestScore=score;best=sample;}
        }
        return best;
    }
    static float Axis(AxisControl control) {float v=control.ReadValue();return Finite(v)?Mathf.Clamp01(v):0;}
    static bool Finite(float value) {return !float.IsNaN(value)&&!float.IsInfinity(value);}
    static bool Pose(InputControl control,out Vector3 position,out Quaternion rotation) {
        position=Vector3.zero;rotation=Quaternion.identity;
        if(control==null)return false;
        var tracked=control.TryGetChildControl<ButtonControl>("isTracked");
        var state=control.TryGetChildControl<IntegerControl>("trackingState");
        var pos=control.TryGetChildControl<Vector3Control>("position")??control.TryGetChildControl<Vector3Control>("devicePosition");
        var rot=control.TryGetChildControl<QuaternionControl>("rotation")??control.TryGetChildControl<QuaternionControl>("deviceRotation");
        int required=(int)(InputTrackingState.Position|InputTrackingState.Rotation);
        if(tracked==null || !tracked.isPressed || state==null || (state.ReadValue()&required)!=required || pos==null || rot==null)return false;
        var p=pos.ReadValue();var q=rot.ReadValue();float norm=q.x*q.x+q.y*q.y+q.z*q.z+q.w*q.w;
        if(!Finite(p.x)||!Finite(p.y)||!Finite(p.z)||!Finite(norm)||norm<.9f||norm>1.1f)return false;
        position=p;rotation=q;return true;
    }
}
}
