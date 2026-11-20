using UnityEditor;
using UnityEditor.Build.Reporting;
using System;
using System.IO;
namespace RoboStudioVR.Editor {
public static class BuildRoboData {
    public static void Build() {
        const string materialPath="Assets/Resources/RoboDataPointer.mat";
        if(AssetDatabase.LoadAssetAtPath<UnityEngine.Material>(materialPath)==null) {
            var shader=UnityEngine.Shader.Find("Universal Render Pipeline/Unlit");
            if(shader==null)throw new Exception("Pointer shader unavailable");
            AssetDatabase.CreateAsset(new UnityEngine.Material(shader),materialPath);
            AssetDatabase.SaveAssets();
        }
        UnityEditor.XR.OpenXR.Features.FeatureHelpers.RefreshFeatures(BuildTargetGroup.Android);
        var xr=UnityEngine.XR.OpenXR.OpenXRSettings.GetSettingsForBuildTargetGroup(BuildTargetGroup.Android);
        var cameraFeature=xr.GetFeature<UnityEngine.XR.OpenXR.Features.Meta.ARCameraFeature>();
        var sessionFeature=xr.GetFeature<UnityEngine.XR.OpenXR.Features.Meta.ARSessionFeature>();
        if(cameraFeature==null || sessionFeature==null)throw new Exception("Meta passthrough features unavailable");
        xr.GetFeature<UnityEngine.XR.OpenXR.Features.CompositionLayers.OpenXRCompositionLayersFeature>().enabled=true;
        PlayerSettings.Android.minSdkVersion=AndroidSdkVersions.AndroidApiLevel32;
        cameraFeature.enabled=true;
        sessionFeature.enabled=true;
        EditorUtility.SetDirty(xr);
        AssetDatabase.SaveAssets();
        var icon=AssetDatabase.LoadAssetAtPath<UnityEngine.Texture2D>("Assets/Branding/RoboDataIcon.png");
        var foreground=AssetDatabase.LoadAssetAtPath<UnityEngine.Texture2D>("Assets/Branding/RoboDataForeground.png");
        var background=AssetDatabase.LoadAssetAtPath<UnityEngine.Texture2D>("Assets/Branding/RoboDataBackground.png");
        if(icon==null || foreground==null || background==null)throw new Exception("RoboData icons missing");
        var android=UnityEditor.Build.NamedBuildTarget.Android;
        foreach(var kind in PlayerSettings.GetSupportedIconKinds(android)) {
            var icons=PlayerSettings.GetPlatformIcons(android,kind);
            foreach(var slot in icons) {
                if(slot.minLayerCount>1){slot.SetTexture(background,0);slot.SetTexture(foreground,1);}
                else slot.SetTexture(icon);
            }
            PlayerSettings.SetPlatformIcons(android,kind,icons);
        }
        PlayerSettings.productName="RoboData";
        PlayerSettings.bundleVersion="0.3.9";
        PlayerSettings.Android.bundleVersionCode=12;
        PlayerSettings.Android.targetArchitectures=AndroidArchitecture.ARM64;
        PlayerSettings.SetScriptingBackend(UnityEditor.Build.NamedBuildTarget.Android,ScriptingImplementation.IL2CPP);
        var output=Environment.GetEnvironmentVariable("ROBODATA_APK")??Path.GetFullPath(Path.Combine(UnityEngine.Application.dataPath,"../../artifacts/apk/RoboData.apk"));
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output)));
        var report=BuildPipeline.BuildPlayer(new BuildPlayerOptions {scenes=new[]{"Assets/Scenes/ControllerDiagnostics.unity"},locationPathName=output,target=BuildTarget.Android,options=BuildOptions.None});
        if(report.summary.result!=BuildResult.Succeeded)throw new Exception("RoboData build failed: "+report.summary.result);
    }
}}
