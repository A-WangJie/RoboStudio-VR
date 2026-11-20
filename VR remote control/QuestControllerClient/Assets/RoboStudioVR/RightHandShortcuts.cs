namespace RoboStudioVR {
// Require a neutral sample after interruption, then consume one press per release.
public sealed class RightHandShortcuts {
    private int deviceId=-1;
    private bool armed;

    public void Reset() { deviceId=-1; armed=false; }

    public string Read(ControllerInput.Sample right,bool available) {
        if(!available || !right.connected || !right.tracked) { Reset(); return null; }
        if(deviceId!=right.deviceId) { deviceId=right.deviceId; armed=false; }
        if(!right.primary && !right.secondary) { armed=true; return null; }
        if(!armed)return null;
        armed=false;
        // An ambiguous chord must not start or reset motion.
        if(right.primary && right.secondary)return null;
        return right.primary?"follow":"grasp";
    }
}
}
