using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.XR;

namespace RoboStudioVR {
// Compact world-space console. Controller rays work without an extra XR UI package.
public sealed class RoboDataPanel : MonoBehaviour {
    QuestTelemetrySender sender;
    Canvas canvas; RectTransform panel;
    Font font; Text status,networkLatency,hostStatus,streamStatus,armStatus,captureStatus,detail,feedback,taskLabel;
    readonly Image[] signalBars=new Image[3];
    GameObject home, data, keyboard;
    string mode,ip,port,code,task,editing="";
    Text ipLabel,codeLabel;
    readonly List<Button> targets=new List<Button>();
    readonly bool[] pressed=new bool[2];
    readonly LineRenderer[] rays=new LineRenderer[2];
    readonly GameObject[] reticles=new GameObject[2];
    readonly bool[] aimLogged=new bool[2];
    float refresh, fps;
    bool located;
    int configurationRevision;
    float locateAfter=float.PositiveInfinity;
    float nextSubsystemCheck;
    readonly List<XRInputSubsystem> inputSubsystems=new List<XRInputSubsystem>();
    readonly HashSet<XRInputSubsystem> subscribedSubsystems=new HashSet<XRInputSubsystem>();
    Camera camera;
    Color ink=new Color(.035f,.065f,.09f), muted=new Color(.13f,.19f,.23f);
    IEnumerator Start() {
        sender=GetComponent<QuestTelemetrySender>(); camera=Camera.main;
        XRSettings.eyeTextureResolutionScale=1.2f;
        font=Resources.Load<Font>("RoboDataFont");
        if(font==null)font=Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        mode=PlayerPrefs.GetString("rd.mode","usb");ip=PlayerPrefs.GetString("rd.host","");port=PlayerPrefs.GetString("rd.port","8766");code=PlayerPrefs.GetString("rd.code","");task=PlayerPrefs.GetString("rd.task","");
        var old=GetComponent<ControllerDiagnostics>(); if(old.display!=null)old.display.GetComponentInParent<Canvas>().gameObject.SetActive(false);
        panel=Make("RoboData",null,0,0,1000,680).GetComponent<RectTransform>();
        canvas=panel.gameObject.AddComponent<Canvas>();canvas.renderMode=RenderMode.WorldSpace;canvas.worldCamera=camera;
        panel.localScale=Vector3.one*.001f;
        var scaler=panel.gameObject.AddComponent<CanvasScaler>();
        scaler.dynamicPixelsPerUnit=2f;
        panel.gameObject.AddComponent<Image>().color=new Color(.78f,.81f,.83f);
        Label(panel,"Robo<size=36><color=#8C6500>Data</color></size>",28,18,500,55,36);
        status=Label(panel,"FPS —",28,76,140,36,20);
        for(int i=0;i<3;i++) {
            float height=9+i*8;
            signalBars[i]=Make("Network signal "+(i+1),panel,185+i*13,104-height,9,height).AddComponent<Image>();
            signalBars[i].raycastTarget=false;
            signalBars[i].color=new Color(.48f,.54f,.55f);
        }
        networkLatency=Label(panel,"— ms",237,76,390,36,20);
        Button(panel,"控制台",700,24,120,40,()=>Show(false));Button(panel,"采集详情",835,24,135,40,()=>Show(true));
        home=Make("Control",panel,0,125,1000,470);
        Label(home.transform,"姿态控制",28,0,900,30,22);
        Button(home.transform,"启动 / 重置跟随  [A]",28,46,296,62,()=>sender.Command("follow"));
        Button(home.transform,"待机 / 零位姿态",352,46,296,62,()=>sender.Command("zero"));
        Button(home.transform,"复位 / VR 抓取位姿  [B]",676,46,296,62,()=>sender.Command("grasp"));
        Label(home.transform,"无线连接",28,135,280,34,22);
        Label(home.transform,"配对码",28,181,280,28,18);
        codeLabel=Button(home.transform,"",28,215,280,56,()=>Edit("code")).GetComponentInChildren<Text>();
        Label(home.transform,"主机 IP",28,283,280,28,18);
        ipLabel=Button(home.transform,"",28,317,280,56,()=>Edit("ip")).GetComponentInChildren<Text>();
        Button(home.transform,"连接",28,393,280,56,()=>sender.Configure("wifi",ip,"8766",code));
        Label(home.transform,"主机状态",352,135,280,34,22);
        var hostBox=Make("Host status",home.transform,352,191,280,94);
        hostBox.AddComponent<Image>().color=new Color(.69f,.75f,.79f);
        Label(hostBox.transform,"上位机",14,4,100,40,20);
        hostStatus=Label(hostBox.transform,"未连接",114,4,152,40,20);hostStatus.alignment=TextAnchor.MiddleRight;
        Label(hostBox.transform,"数据流",14,50,100,40,20);
        streamStatus=Label(hostBox.transform,"断流",114,50,152,40,20);streamStatus.alignment=TextAnchor.MiddleRight;
        var armBox=Make("Arm status",home.transform,352,303,280,56);
        armBox.AddComponent<Image>().color=new Color(.69f,.75f,.79f);
        Label(armBox.transform,"机械臂",14,4,100,48,20);
        armStatus=Label(armBox.transform,"断开",114,4,152,48,20);armStatus.alignment=TextAnchor.MiddleRight;
        Button(home.transform,"停止跟随",352,393,280,56,()=>sender.Command("stop"));
        Label(home.transform,"采集",676,135,296,34,22);
        captureStatus=Label(home.transform,"未录制 · 0 帧",676,181,296,108,21);
        Label(home.transform,"任务",676,303,296,30,22);
        taskLabel=Button(home.transform,"",676,345,296,64,()=>Edit("task")).GetComponentInChildren<Text>();
        Label(home.transform,"由 RS 开始 / 结束录制",676,416,296,34,16);
        data=Make("Data",panel,28,135,944,440);
        detail=Label(data.transform,"等待数据",0,0,940,440,21);
        feedback=Label(panel,"先复位到抓取位姿，再松开握键并启动跟随。",28,590,720,66,18);
        var quit=Button(panel,"退出 APP",800,606,170,46,()=>{sender.Command("stop");Application.Quit();});quit.GetComponent<Image>().color=new Color(.78f,.25f,.23f);quit.GetComponentInChildren<Text>().color=Color.white;
        keyboard=Make("Keyboard",panel,20,150,960,420);keyboard.AddComponent<Image>().color=new Color(.74f,.78f,.81f);keyboard.SetActive(false);
        var chars="1234567890qwertyuiopasdfghjkl_zxcvbnm.-";
        for(int i=0;i<chars.Length;i++){var c=chars[i].ToString();Button(keyboard.transform,c.ToUpperInvariant(),15+i%10*93,65+i/10*62,83,52,()=>Append(c));}
        Button(keyboard.transform,"空格",15,330,190,55,()=>Append(" "));
        Button(keyboard.transform,"退格",225,330,190,55,()=>{var value=GetValue();SetValue(value.Length>0?value.Substring(0,value.Length-1):"");});
        Button(keyboard.transform,"清空",435,330,190,55,()=>SetValue(""));
        Button(keyboard.transform,"完成",645,330,290,55,()=>{keyboard.SetActive(false);Show(false);PlayerPrefs.SetString("rd.task",task);PlayerPrefs.Save();});
        Label(keyboard.transform,"输入 IP / 配对码 / 任务名（字母、数字）",15,12,930,40,20);
        for(int i=0;i<2;i++) {
            var go=new GameObject("RoboData pointer");rays[i]=go.AddComponent<LineRenderer>();
            rays[i].positionCount=2;rays[i].startWidth=.0012f;rays[i].endWidth=.0012f;
            rays[i].material=new Material(Resources.Load<Material>("RoboDataPointer"));
            rays[i].material.color=new Color(.08f,.32f,.48f);
            reticles[i]=new GameObject("RoboData aim marker");
            var ring=reticles[i].AddComponent<LineRenderer>();
            ring.useWorldSpace=false;ring.loop=true;ring.positionCount=24;
            ring.startWidth=ring.endWidth=.0012f;ring.sharedMaterial=rays[i].material;
            for(int j=0;j<24;j++){float a=j*Mathf.PI*2/24;ring.SetPosition(j,new Vector3(Mathf.Cos(a)*.0045f,Mathf.Sin(a)*.0045f,0));}
            reticles[i].SetActive(false);
        }
        UpdateFields();Show(false);
        panel.gameObject.SetActive(false);
        yield return null;
        SchedulePlacement(.7f);
    }
    // The Meta button remains owned by Quest. React to the resulting OpenXR origin update.
    void SchedulePlacement(float delay){located=false;locateAfter=Time.unscaledTime+delay;}
    void OnTrackingOriginUpdated(XRInputSubsystem subsystem){
        SchedulePlacement(.25f);
        Debug.Log("[RoboData] System tracking origin changed; panel placement scheduled");
    }
    void SubscribeTrackingOrigin(){
        if(Time.unscaledTime<nextSubsystemCheck)return;
        nextSubsystemCheck=Time.unscaledTime+1f;
        SubsystemManager.GetSubsystems(inputSubsystems);
        foreach(var subsystem in inputSubsystems)
            if(subscribedSubsystems.Add(subsystem))subsystem.trackingOriginUpdated+=OnTrackingOriginUpdated;
    }
    void Recenter(){
        if(panel==null || camera==null)return;
        // Place the centre 22 degrees below the current gaze, then leave it world-locked.
        var direction=Quaternion.AngleAxis(22f,camera.transform.right)*camera.transform.forward;
        panel.position=camera.transform.position+direction.normalized*1.15f;
        panel.rotation=Quaternion.LookRotation(direction,Vector3.up);
        panel.gameObject.SetActive(true);
        Debug.Log("[RoboData] Panel placed below current gaze");
    }
    GameObject Make(string name,Transform parent,float x,float y,float w,float h){var go=new GameObject(name,typeof(RectTransform));var r=go.GetComponent<RectTransform>();r.SetParent(parent,false);r.sizeDelta=new Vector2(w,h);if(parent!=null){r.anchorMin=r.anchorMax=new Vector2(0,1);r.pivot=new Vector2(0,1);r.anchoredPosition=new Vector2(x,-y);}return go;}
    Text Label(Transform parent,string text,float x,float y,float w,float h,int size){var go=Make("Label",parent,x,y,w,h);var t=go.AddComponent<Text>();t.font=font;t.text=text;t.fontSize=size<30?size+2:size;t.fontStyle=FontStyle.Bold;t.color=ink;t.raycastTarget=false;t.supportRichText=true;t.verticalOverflow=VerticalWrapMode.Overflow;t.alignment=TextAnchor.MiddleLeft;return t;}
    Button Button(Transform parent,string title,float x,float y,float w,float h,UnityEngine.Events.UnityAction action){var go=Make(title,parent,x,y,w,h);go.AddComponent<Image>().color=new Color(.63f,.70f,.75f);var edge=go.AddComponent<Shadow>();edge.effectColor=new Color(.1f,.17f,.22f,.28f);edge.effectDistance=new Vector2(0,-1.5f);var b=go.AddComponent<Button>();var outline=go.AddComponent<Outline>();outline.effectColor=new Color(.7f,.58f,.2f);outline.effectDistance=new Vector2(2,-2);outline.enabled=false;b.onClick.AddListener(action);var label=Label(go.transform,title,8,0,w-16,h,20);label.alignment=TextAnchor.MiddleCenter;targets.Add(b);return b;}
    Text StatusBox(Transform parent,string text,float x,float y,float width,float height){
        var box=Make("Connection status",parent,x,y,width,height);
        box.AddComponent<Image>().color=new Color(.69f,.75f,.79f);
        return Label(box.transform,text,14,5,width-28,height-10,21);
    }
    void Show(bool second){if(keyboard!=null)keyboard.SetActive(false);sender.EditingText=false;home.SetActive(!second);data.SetActive(second);}
    void Edit(string field){editing=field;sender.EditingText=true;home.SetActive(false);data.SetActive(false);keyboard.SetActive(true);}
    string GetValue(){return editing=="ip"?ip:editing=="port"?port:editing=="code"?code:task;}
    void SetValue(string value){if(value.Length>80)return;if(editing=="ip")ip=value;else if(editing=="port")port=value;else if(editing=="code")code=value;else task=value;sender.TaskName=task;UpdateFields();feedback.text="输入："+GetValue();}
    void Append(string c){SetValue(GetValue()+c);}
    void UpdateFields(){
        ipLabel.text=ip==""?"输入主机 IP":ip;
        codeLabel.text=code==""?"输入配对码":code;
        taskLabel.text=task==""?"输入任务名":task;
    }
    void Update(){
        if(panel==null || sender==null || camera==null)return;
        if(configurationRevision!=sender.ConfigurationRevision){
            configurationRevision=sender.ConfigurationRevision;
            mode=PlayerPrefs.GetString("rd.mode","usb");ip=PlayerPrefs.GetString("rd.host","");port=PlayerPrefs.GetString("rd.port","8766");code=PlayerPrefs.GetString("rd.code","");UpdateFields();
        }
        SubscribeTrackingOrigin();
        bool headTracked;
        if(!located && Application.isFocused && Time.unscaledTime>locateAfter && InputDevices.GetDeviceAtXRNode(XRNode.Head).TryGetFeatureValue(CommonUsages.isTracked,out headTracked) && headTracked){Recenter();located=true;}
        fps=Mathf.Lerp(fps,1f/Mathf.Max(Time.unscaledDeltaTime,.001f),.05f);
        sender.UiInteracting=keyboard.activeSelf;
        sender.EditingText=keyboard.activeSelf;
        foreach(var button in targets)button.GetComponent<Outline>().enabled=false;
        for(int i=0;i<2;i++)Pointer(i);
        if(Time.unscaledTime<refresh)return;refresh=Time.unscaledTime+.2f;
        status.text=$"FPS {fps:F0}";
        bool measured=sender.HasLatencySample;
        networkLatency.text=measured?$"{sender.RttMs:F0} ms":"— ms";
        // Measured round-trip quality, not Wi-Fi radio RSSI. No invented animation.
        int bars=!measured?0:sender.RttMs<=50?3:sender.RttMs<=100?2:1;
        for(int i=0;i<3;i++)signalBars[i].color=i<bars?new Color(.04f,.66f,.29f):new Color(.48f,.54f,.55f);
        var h=sender.Host;var sim=h?.simulation;var rec=h?.recording;
        bool fresh=sender.HasFreshHostStatus;
        hostStatus.text=fresh && sim!=null && sim.online?"已连接":"未连接";
        streamStatus.text=fresh && h.inputLive?(sender.Transport=="usb"?"USB":"Wi-Fi"):"断流";
        armStatus.text=!fresh?"断开":h.armMode=="real"?"真机":sim!=null&&sim.online?"仿真":"断开";
        captureStatus.text=$"{(rec!=null&&rec.active?"录制中":"未录制")}\n{rec?.frames??0} 帧 · {rec?.duration??0:F1} 秒";
        captureStatus.color=rec!=null&&rec.active?new Color(.04f,.31f,.20f):ink;
        if(!keyboard.activeSelf)feedback.text=sender.Feedback+"\n长按 Meta 键重置视角并召回面板；右握键按住跟随。";
        detail.text=$"数据发送：{sender.Frames} 帧 · 30 Hz 上限\n{(Application.isFocused?"应用焦点有效":"焦点丢失，追踪无效")}\n"+Hand("左手",XRNode.LeftHand)+Hand("右手",XRNode.RightHand)+$"\n任务：{rec?.task??task}\n采集：{rec?.duration??0:F1} s / {rec?.frames??0} 帧\n{sim?.message}\n位置：米 · 旋转：XYZW · 本地追踪空间";
    }
    string Hand(string name,XRNode node){
        var sample=ControllerInput.Read(node);bool valid=Application.isFocused && sample.tracked;
        return $"\n{name}：{(valid?"有效":sample.connected?"等待追踪 · 自动恢复":"未连接 · 自动检测")}\n位置 {(valid?sample.position.ToString("F3"):"—")}  旋转 {(valid?sample.rotation.ToString("F2"):"—")}\n握键 {sample.grip:F2}  扳机 {sample.trigger:F2}\n";
    }
    void Pointer(int index){
        if(rays[index]==null)return;
        var sample=ControllerInput.Read(index==0?XRNode.LeftHand:XRNode.RightHand);
        if(!Application.isFocused || !panel.gameObject.activeSelf || !sample.aimTracked){
            rays[index].enabled=false;reticles[index].SetActive(false);pressed[index]=true;return;
        }
        if(!aimLogged[index]){Debug.Log("[RoboData] UI uses tracked OpenXR aim pose: "+(index==0?"left":"right"));aimLogged[index]=true;}
        Vector3 pos=sample.aimPosition;Quaternion rot=sample.aimRotation;
        var rig=camera.transform.parent;var origin=rig?rig.TransformPoint(pos):pos;var direction=(rig?rig.rotation*rot:rot)*Vector3.forward;var ray=new Ray(origin,direction);float distance;
        bool hit=new Plane(panel.forward,panel.position).Raycast(ray,out distance)&&distance>0&&distance<4;
        var point=ray.GetPoint(hit?distance:1.5f);rays[index].enabled=true;rays[index].SetPosition(0,origin);rays[index].SetPosition(1,point);
        var onPanel=hit && panel.rect.Contains(panel.InverseTransformPoint(point));
        reticles[index].SetActive(onPanel);
        if(onPanel){reticles[index].transform.position=point-panel.forward*.003f;reticles[index].transform.rotation=panel.rotation;}
        bool down=sample.trigger>.65f;
        if(hit && panel.rect.Contains(panel.InverseTransformPoint(point)))sender.UiInteracting=true;
        if(hit)for(int j=targets.Count-1;j>=0;j--){var b=targets[j];if(!b.gameObject.activeInHierarchy||!b.interactable)continue;var r=(RectTransform)b.transform;if(r.rect.Contains(r.InverseTransformPoint(point))){b.GetComponent<Outline>().enabled=true;if(down&&!pressed[index])b.onClick.Invoke();break;}}
        pressed[index]=down;
    }
    void OnDestroy(){foreach(var marker in reticles)if(marker!=null)Destroy(marker);foreach(var subsystem in subscribedSubsystems)subsystem.trackingOriginUpdated-=OnTrackingOriginUpdated;foreach(var ray in rays)if(ray!=null){Destroy(ray.material);Destroy(ray.gameObject);}}
}
}
