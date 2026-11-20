using System;
using UnityEngine;

namespace RoboStudioVR.Editor {
public static class ValidateRightHandShortcuts {
    static void Check(bool value,string message) { if(!value)throw new Exception("RD shortcuts: "+message); }
    public static void RunChecks() {
        var keys=new RightHandShortcuts();
        var right=new ControllerInput.Sample {deviceId=1,connected=true,tracked=true};
        Check(keys.Read(right,true)==null,"neutral startup");
        right.primary=true;
        Check(keys.Read(right,true)=="follow","A starts/resets following");
        for(int i=0;i<120;i++)Check(keys.Read(right,true)==null,"held A must not repeat");
        right.primary=false;keys.Read(right,true);right.secondary=true;
        Check(keys.Read(right,true)=="grasp","B resets to VR grasp pose");
        for(int i=0;i<120;i++)Check(keys.Read(right,true)==null,"held B must not repeat");
        right.secondary=false;keys.Read(right,true);right.primary=true;
        Check(keys.Read(right,true)=="follow","release allows another press");
        keys.Reset();
        Check(keys.Read(right,true)==null,"held button on startup/reconfiguration");
        right.primary=false;keys.Read(right,true);right.primary=true;
        Check(keys.Read(right,true)=="follow","press after neutral startup");
        Check(keys.Read(right,false)==null,"focus/network/UI/preparation unavailable");
        Check(keys.Read(right,true)==null,"held button on availability recovery");
        right.primary=false;keys.Read(right,true);right.primary=true;
        Check(keys.Read(right,true)=="follow","press after availability recovery");
        right.tracked=false;Check(keys.Read(right,true)==null,"tracking loss");
        right.tracked=true;Check(keys.Read(right,true)==null,"held button on tracking recovery");
        right.primary=false;keys.Read(right,true);
        right.connected=false;Check(keys.Read(right,true)==null,"controller disconnect");
        right.connected=true;right.secondary=true;
        Check(keys.Read(right,true)==null,"held button on reconnect");
        right.secondary=false;keys.Read(right,true);right.deviceId=2;right.secondary=true;
        Check(keys.Read(right,true)==null,"held button on device replacement");
        right.secondary=false;keys.Read(right,true);right.secondary=true;
        Check(keys.Read(right,true)=="grasp","B works after replacement release");
        right.secondary=false;keys.Read(right,true);right.primary=right.secondary=true;
        Check(keys.Read(right,true)==null,"simultaneous A+B ignored");
        right.primary=false;Check(keys.Read(right,true)==null,"partial chord release ignored");
        right.secondary=false;keys.Read(right,true);right.secondary=true;
        Check(keys.Read(right,true)=="grasp","full chord release re-arms");
        right.secondary=false;keys.Read(right,true);right.primary=true;
        Check(keys.Read(right,false)==null,"unavailable press is consumed");
        right.primary=false;keys.Read(right,true);
        Check(keys.Read(right,true)==null,"unavailable press is not replayed");
        Debug.Log("RoboData right-hand shortcuts: PASS (A=follow, B=grasp, hold, recovery, replacement, chord, no replay)");
    }
    public static void Build() { RunChecks(); BuildRoboData.Build(); }
}
}
