using System.Text;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.XR;
using UnityEngine.Rendering;
using System.Collections.Generic;

namespace RoboStudioVR
{
    // Read-only diagnostics and telemetry. No robot commands are issued.
    public sealed class ControllerDiagnostics : MonoBehaviour
    {
        public Text display;
        private QuestTelemetrySender telemetry;
        private float nextRefresh;
        private float nextDiagnostic;
        private int renderedFrames;
        private readonly List<XRDisplaySubsystem> xrDisplays = new List<XRDisplaySubsystem>();
        private void Awake()
        {
            telemetry = GetComponent<QuestTelemetrySender>();
            if (telemetry == null) telemetry = gameObject.AddComponent<QuestTelemetrySender>();
            gameObject.AddComponent<RoboDataPanel>();
            Debug.Log("[QuestCheck v2] Awake scene=" + gameObject.scene.name + " display=" + (display != null));
            var camera = Camera.main;
            if (camera != null)
            {
                camera.backgroundColor = Color.clear;
                camera.allowHDR = false;
                camera.gameObject.AddComponent<UnityEngine.XR.ARFoundation.ARCameraManager>();
                new GameObject("RoboData AR Session").AddComponent<UnityEngine.XR.ARFoundation.ARSession>();
                camera.clearFlags = CameraClearFlags.SolidColor;
            }
            if (display != null)
            {
                display.verticalOverflow = VerticalWrapMode.Overflow;
                var canvas = display.GetComponentInParent<Canvas>();
                if (canvas != null) canvas.worldCamera = camera;
            }
        }
        private void OnEnable() { RenderPipelineManager.endCameraRendering += OnCameraRendered; }
        private void OnDisable() { RenderPipelineManager.endCameraRendering -= OnCameraRendered; }
        private void OnCameraRendered(ScriptableRenderContext context, Camera camera)
        {
            if (camera == Camera.main) renderedFrames++;
        }
        private void LogDiagnostics()
        {
            if (Time.unscaledTime < nextDiagnostic) return;
            nextDiagnostic = Time.unscaledTime + 2f;
            SubsystemManager.GetSubsystems(xrDisplays);
            Debug.Log("[QuestCheck v2] heartbeat focus=" + Application.isFocused
                + " camera=" + (Camera.main != null) + " rendered=" + renderedFrames
                + " xr=" + (xrDisplays.Count > 0 && xrDisplays[0].running)
                + " text=" + (display != null && display.isActiveAndEnabled)
                + " vertices=" + (display == null ? 0 : display.cachedTextGenerator.vertexCount)
                + " left=" + InputDevices.GetDeviceAtXRNode(XRNode.LeftHand).isValid
                + " right=" + InputDevices.GetDeviceAtXRNode(XRNode.RightHand).isValid);
        }
        private readonly StringBuilder text = new StringBuilder(1200);

        private void Update()
        {
            if (GetComponent<RoboDataPanel>() != null) return;
            LogDiagnostics();
            if (display == null || Time.unscaledTime < nextRefresh) return;
            nextRefresh = Time.unscaledTime + 0.1f;
            text.Clear();
            text.AppendLine("RoboStudio | Quest Input Check v2");
            text.AppendLine("LOCAL tracking space | meters | quaternion XYZW");
            text.AppendLine(telemetry.Status);
            text.AppendLine(Application.isFocused ? "Focus: ACTIVE" : "Focus: LOST - input invalid");
            AppendHand("LEFT", XRNode.LeftHand);
            AppendHand("RIGHT", XRNode.RightHand);
            text.AppendLine("Grip / trigger: 0 released -> 1 fully pressed");
            text.AppendLine("Read-only check. Robot is NOT connected.");
            display.text = text.ToString();
        }

        private void AppendHand(string label, XRNode node)
        {
            var device = InputDevices.GetDeviceAtXRNode(node);
            text.AppendLine();
            text.AppendLine(label + " | " + (device.isValid ? device.name : "NOT CONNECTED"));
            if (!device.isValid) return;
            bool tracked;
            bool hasTracked = device.TryGetFeatureValue(CommonUsages.isTracked, out tracked);
            InputTrackingState tracking;
            bool hasState = device.TryGetFeatureValue(CommonUsages.trackingState, out tracking);
            bool valid = Application.isFocused && hasTracked && tracked && hasState;
            Vector3 position;
            Quaternion rotation;
            bool hasPosition = device.TryGetFeatureValue(CommonUsages.devicePosition, out position);
            bool hasRotation = device.TryGetFeatureValue(CommonUsages.deviceRotation, out rotation);
            text.AppendLine("Position: " + (valid && hasPosition && (tracking & InputTrackingState.Position) != 0
                ? position.ToString("F3") : "UNTRACKED"));
            text.AppendLine("Rotation: " + (valid && hasRotation && (tracking & InputTrackingState.Rotation) != 0
                ? rotation.ToString("F3") : "UNTRACKED"));
            float trigger, grip;
            bool primary, secondary;
            Vector2 stick;
            text.AppendLine("Trigger: " + (device.TryGetFeatureValue(CommonUsages.trigger, out trigger) ? trigger.ToString("F2") : "N/A")
                + "   Grip: " + (device.TryGetFeatureValue(CommonUsages.grip, out grip) ? grip.ToString("F2") : "N/A"));
            text.AppendLine("Primary: " + (device.TryGetFeatureValue(CommonUsages.primaryButton, out primary) ? primary.ToString() : "N/A")
                + "   Secondary: " + (device.TryGetFeatureValue(CommonUsages.secondaryButton, out secondary) ? secondary.ToString() : "N/A"));
            text.AppendLine("Stick: " + (device.TryGetFeatureValue(CommonUsages.primary2DAxis, out stick) ? stick.ToString("F2") : "N/A"));
        }
    }
}
