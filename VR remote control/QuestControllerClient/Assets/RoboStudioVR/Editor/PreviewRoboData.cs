using System.Collections;
using System.Reflection;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;

namespace RoboStudioVR.Editor {
// Render the actual runtime layout with illustrative status values; never connect a device.
public static class PreviewRoboData {
    public static void Render() {
        EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
        var cameraObject=new GameObject("Preview Camera",typeof(Camera));
        cameraObject.tag="MainCamera";
        var camera=cameraObject.GetComponent<Camera>();
        camera.orthographic=true;camera.orthographicSize=.355f;
        camera.transform.position=new Vector3(0,0,-2);
        camera.clearFlags=CameraClearFlags.SolidColor;camera.backgroundColor=new Color(.91f,.93f,.94f);
        var host=new GameObject("Preview Host");
        host.AddComponent<QuestTelemetrySender>();
        host.AddComponent<ControllerDiagnostics>();
        var panel=host.AddComponent<RoboDataPanel>();
        var flags=BindingFlags.Instance|BindingFlags.NonPublic;
        var start=(IEnumerator)typeof(RoboDataPanel).GetMethod("Start",flags).Invoke(panel,null);
        start.MoveNext();
        var rect=(RectTransform)typeof(RoboDataPanel).GetField("panel",flags).GetValue(panel);
        rect.gameObject.SetActive(true);
        rect.position=Vector3.zero;rect.rotation=Quaternion.identity;
        var target=new RenderTexture(1600,1088,24);
        camera.targetTexture=target;
        var directory=Path.GetFullPath("../docs/previews");Directory.CreateDirectory(directory);
        for(int example=0;example<2;example++) {
            bool online=example==0;
            ((Text)typeof(RoboDataPanel).GetField("status",flags).GetValue(panel)).text="FPS 72";
            ((Text)typeof(RoboDataPanel).GetField("networkLatency",flags).GetValue(panel)).text=online?"38 ms":"— ms";
            ((Text)typeof(RoboDataPanel).GetField("hostStatus",flags).GetValue(panel)).text=online?"已连接\nVR 模式 · 未跟随\n采集：未录制 · 0 帧":"连接中…\n主机状态待确认\n采集：未录制 · 0 帧";
            ((Text)typeof(RoboDataPanel).GetField("feedback",flags).GetValue(panel)).text="长按 Meta 键重置视角并召回面板；右握键按住跟随。";
            foreach(var image in (Image[])typeof(RoboDataPanel).GetField("signalBars",flags).GetValue(panel))image.color=online?new Color(.04f,.66f,.29f):new Color(.48f,.54f,.55f);
            Canvas.ForceUpdateCanvases();
            foreach(var text in rect.GetComponentsInChildren<Text>())text.Rebuild(CanvasUpdate.PreRender);
            Canvas.ForceUpdateCanvases();
            camera.Render();
            RenderTexture.active=target;
            var imageData=new Texture2D(1600,1088,TextureFormat.RGB24,false);
            imageData.ReadPixels(new Rect(0,0,1600,1088),0,0);imageData.Apply();
            File.WriteAllBytes(Path.Combine(directory,online?"RoboData-0.3.5-connected.png":"RoboData-0.3.5-disconnected.png"),imageData.EncodeToPNG());
            Object.DestroyImmediate(imageData);
        }
        Debug.Log("RoboData UI previews rendered: "+directory);
        EditorApplication.Exit(0);
    }
}}
