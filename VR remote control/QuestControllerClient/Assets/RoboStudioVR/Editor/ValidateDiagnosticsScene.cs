using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace RoboStudioVR.Editor
{
    // Validate the saved scene entering the player, including its camera and UI references.
    public sealed class ValidateDiagnosticsScene : IProcessSceneWithReport
    {
        public int callbackOrder => 0;

        public void OnProcessScene(Scene scene, BuildReport report)
        {
            if (report == null || scene.path != "Assets/Scenes/ControllerDiagnostics.unity") return;
            foreach (var root in scene.GetRootGameObjects())
            foreach (var diagnostics in root.GetComponentsInChildren<ControllerDiagnostics>(true))
            {
                var display = diagnostics.display;
                var camera = display == null ? null : display.GetComponentInParent<Camera>();
                var canvas = display == null ? null : display.GetComponentInParent<Canvas>();
                if (diagnostics.isActiveAndEnabled && display != null && display.isActiveAndEnabled
                    && camera != null && camera.isActiveAndEnabled && camera.CompareTag("MainCamera")
                    && canvas != null && canvas.isActiveAndEnabled && canvas.renderMode == RenderMode.WorldSpace)
                    return;
            }
            throw new BuildFailedException("ControllerDiagnostics scene is empty or missing its active diagnostic script, text, world-space canvas or MainCamera. Restore the diagnostic scene before building.");
        }
    }
}
