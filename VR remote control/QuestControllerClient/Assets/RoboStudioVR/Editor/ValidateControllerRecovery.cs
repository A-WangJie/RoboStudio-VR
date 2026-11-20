using System;
using UnityEditor;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.Controls;
using UnityEngine.InputSystem.LowLevel;
using UnityEngine.XR;
using InputDevice = UnityEngine.InputSystem.InputDevice;
using UnityEngine.XR.OpenXR.Features.Interactions;

namespace RoboStudioVR.Editor {
// Exercise real Input System device add/remove and tracking changes without a headset.
public static class ValidateControllerRecovery {
    static void Check(bool condition,string message) {if(!condition)throw new Exception("Controller recovery: "+message);}
    static InputDevice Add(bool left) {
        var device=InputSystem.AddDevice("RoboDataRecoveryTestController");
        InputSystem.SetDeviceUsage(device,left?UnityEngine.InputSystem.CommonUsages.LeftHand:UnityEngine.InputSystem.CommonUsages.RightHand);
        return device;
    }
    static void Pose(InputDevice device,string path,bool tracked,Vector3 position) {
        var pose=device.TryGetChildControl<InputControl>(path);
        if(pose is UnityEngine.InputSystem.XR.PoseControl modern)
            InputState.Change(modern,new UnityEngine.InputSystem.XR.PoseState(tracked,(InputTrackingState)(tracked?3:0),position,Quaternion.identity,Vector3.zero,Vector3.zero));
        else
            InputState.Change((UnityEngine.XR.OpenXR.Input.PoseControl)pose,new UnityEngine.XR.OpenXR.Input.Pose {isTracked=tracked,trackingState=(InputTrackingState)(tracked?3:0),position=position,rotation=Quaternion.identity});
    }
    static void Track(InputDevice device,Vector3 position) {
        Pose(device,"devicePose",true,position);Pose(device,"pointer",true,position+Vector3.up*.1f);
        InputState.Change(device.TryGetChildControl<AxisControl>("trigger"),.8f);
        InputState.Change(device.TryGetChildControl<AxisControl>("grip"),.6f);
    }
    public static void Run() {
        typeof(UnityEngine.XR.OpenXR.Input.OpenXRInput).GetMethod("RegisterLayouts",System.Reflection.BindingFlags.Static|System.Reflection.BindingFlags.NonPublic).Invoke(null,null);
        InputSystem.RegisterLayout<OculusTouchControllerProfile.OculusTouchController>("RoboDataRecoveryTestController");
        // The runtime XR descriptor supplies the thumbstick's concrete layout.
        // Supply it explicitly when constructing this device without an XR runtime.
        InputSystem.RegisterLayoutOverride("{\"name\":\"RoboDataRecoveryDescriptor\",\"extend\":\"RoboDataRecoveryTestController\",\"controls\":[{\"name\":\"thumbstick\",\"layout\":\"Stick\"},{\"name\":\"devicePose\",\"offset\":256},{\"name\":\"pointer\",\"offset\":320}]}");
        Check(!ControllerInput.Read(XRNode.RightHand).connected,"startup without controller");
        var first=Add(false);
        Check(ControllerInput.Read(XRNode.RightHand).connected&&!ControllerInput.Read(XRNode.RightHand).tracked,"untracked device detected");
        var position=new Vector3(.1f,.2f,.3f);Track(first,position);
        var sample=ControllerInput.Read(XRNode.RightHand);
        Check(sample.tracked&&sample.aimTracked&&sample.position==position,"late tracking acquisition");
        Check(sample.aimPosition!=sample.position&&sample.trigger>.7f,"aim/grip separation and buttons");
        Pose(first,"devicePose",false,position);Pose(first,"pointer",false,position);
        Check(!ControllerInput.Read(XRNode.RightHand).tracked,"tracking loss");
        Track(first,position);Check(ControllerInput.Read(XRNode.RightHand).tracked,"tracking recovery");
        var second=Add(false);Track(second,position*2);
        Pose(first,"devicePose",false,position);Pose(first,"pointer",false,position);
        Check(ControllerInput.Read(XRNode.RightHand).deviceId==second.deviceId,"skip stale first binding");
        var left=Add(true);Track(left,-position);
        Check(ControllerInput.Read(XRNode.LeftHand).position==-position,"independent left controller");
        InputSystem.RemoveDevice(second);InputSystem.RemoveDevice(first);
        Check(!ControllerInput.Read(XRNode.RightHand).connected,"device removal");
        var replacement=Add(false);Track(replacement,position);
        sample=ControllerInput.Read(XRNode.RightHand);
        Check(sample.tracked&&sample.deviceId==replacement.deviceId,"replacement reconnection");
        Check(!sample.Telemetry(false).tracked&&sample.Telemetry(false).grip==0,"focus loss invalidates control");
        Pose(replacement,"devicePose",false,position);
        var invalid=ControllerInput.Read(XRNode.RightHand).Telemetry(true);
        Check(!invalid.tracked&&invalid.position[0]==0&&invalid.rotation[3]==1,"stale pose not published");
        InputSystem.RemoveDevice(left);InputSystem.RemoveDevice(replacement);
        Debug.Log("RoboData controller recovery: PASS (late appearance, tracking recovery, stale device, left/right, replacement, focus)");
        EditorApplication.Exit(0);
    }
}}
