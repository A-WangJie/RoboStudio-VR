using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.XR;

namespace RoboStudioVR.Editor
{
    public static class CreateDiagnosticsScene
    {
        private const string ScenePath = "Assets/Scenes/ControllerDiagnostics.unity";

        [MenuItem("RoboStudio VR/Create Controller Check Scene")]
        public static void Create()
        {
            if (!EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) return;
            if (AssetDatabase.LoadAssetAtPath<SceneAsset>(ScenePath) != null)
            {
                EditorSceneManager.OpenScene(ScenePath);
                return;
            }
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var rig = new GameObject("Tracking Space");
            var cameraObject = new GameObject("Main Camera", typeof(Camera), typeof(AudioListener));
            cameraObject.tag = "MainCamera";
            cameraObject.transform.SetParent(rig.transform, false);
            var camera = cameraObject.GetComponent<Camera>();
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = new Color(0.035f, 0.055f, 0.08f);
            camera.nearClipPlane = 0.05f;
            var pose = cameraObject.AddComponent<TrackedPoseDriver>();
            pose.positionInput = new InputActionProperty(new InputAction("Head Position", InputActionType.Value, "<XRHMD>/centerEyePosition", expectedControlType: "Vector3"));
            pose.rotationInput = new InputActionProperty(new InputAction("Head Rotation", InputActionType.Value, "<XRHMD>/centerEyeRotation", expectedControlType: "Quaternion"));
            pose.trackingStateInput = new InputActionProperty(new InputAction("Head Tracking", InputActionType.Value, "<XRHMD>/trackingState", expectedControlType: "Integer"));

            var panel = new GameObject("Input Readout", typeof(RectTransform), typeof(Canvas));
            panel.transform.SetParent(cameraObject.transform, false);
            panel.GetComponent<Canvas>().renderMode = RenderMode.WorldSpace;
            var rect = panel.GetComponent<RectTransform>();
            rect.sizeDelta = new Vector2(1000, 800);
            rect.localPosition = new Vector3(0, 0, 1.4f);
            rect.localScale = Vector3.one * 0.0012f;
            var label = new GameObject("Values", typeof(RectTransform), typeof(Text));
            label.transform.SetParent(panel.transform, false);
            var labelRect = label.GetComponent<RectTransform>();
            labelRect.anchorMin = Vector2.zero; labelRect.anchorMax = Vector2.one;
            labelRect.offsetMin = new Vector2(20, 20); labelRect.offsetMax = new Vector2(-20, -20);
            var display = label.GetComponent<Text>();
            display.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            display.fontSize = 27;
            display.color = new Color(0.85f, 0.94f, 1f);
            display.alignment = TextAnchor.UpperLeft;
            display.raycastTarget = false;
            display.text = "Waiting for Quest input...";
            rig.AddComponent<ControllerDiagnostics>().display = display;
            EditorSceneManager.SaveScene(scene, ScenePath);
            Selection.activeGameObject = rig;
            Debug.Log("Controller check scene created. Use this scene in Build Profiles > Scene List before building for Quest.");
        }
    }
}
