using System;
using System.IO;
using System.Collections.Generic;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.XR;

namespace RoboStudioVR
{
    // USB adb reverse maps this loopback endpoint to the computer bridge.
    public sealed class QuestTelemetrySender : MonoBehaviour
    {
        public string endpoint = "ws://127.0.0.1:8766/input";
        public string Status { get; private set; } = "等待连接";
        public string TaskName = "";
        public bool UiInteracting;
        public bool EditingText;
        private readonly RightHandShortcuts shortcuts = new RightHandShortcuts();
        public int ConfigurationRevision { get; private set; }
        private float nextSetupCheck;
        [Serializable] public class ConnectionSetup { public string mode, host, port, code; }
        private void ReadSetup() {
            if(Time.unscaledTime<nextSetupCheck)return;nextSetupCheck=Time.unscaledTime+1;
            var file=Path.Combine(Application.persistentDataPath,"connection-setup.json");
            if(!File.Exists(file))return;
            try {
                var setup=JsonUtility.FromJson<ConnectionSetup>(File.ReadAllText(file));
                if(setup==null || (setup.mode!="usb" && setup.mode!="wifi"))throw new Exception("连接方式无效");
                Configure(setup.mode,setup.host,setup.port,setup.code);
                File.Delete(file);
            } catch(Exception e) {Feedback="读取同步配置失败："+e.GetType().Name;}
        }
        private string pendingCommand;
        private float commandDeadline;
        public string Transport { get; private set; } = "usb";
        public bool Connected => socket != null && socket.State == WebSocketState.Open;
        public float RttMs { get; private set; }
        private long probeStarted, probeId;
        private float nextProbe, lastLatencySample = -100f;
        private bool probePending;
        public bool HasLatencySample => Connected && Time.realtimeSinceStartup-lastLatencySample < 2f;
        private float lastHostStatus=-100f;
        public bool HasFreshHostStatus => Connected && Host!=null && Time.realtimeSinceStartup-lastHostStatus<2f;
        public HostStatus Host { get; private set; }
        public string Feedback { get; private set; } = "";
        public long Frames => sequence;
        private bool connectRequested = true;
        private readonly Queue<string> commands = new Queue<string>();
        [Serializable] public class SimStatus { public bool online, enabled, vrMode, preparing; public string message; }
        [Serializable] public class RecordingStatus { public bool active; public int frames; public float duration; public string task, file, error; }
        [Serializable] public class HostStatus { public string type, message, id, armMode; public bool ok, inputLive; public long echoTimeMs, probeId; public SimStatus simulation; public RecordingStatus recording; }
        public void Configure(string mode, string host, string port, string code)
        {
            int number;
            if (!int.TryParse(port,out number) || number<1024 || number>65535) { Feedback="端口应为 1024–65535"; return; }
            host=host.Trim();
            if(mode=="wifi" && (Uri.CheckHostName(host)==UriHostNameType.Unknown || host.Contains("/"))) { Feedback="请输入有效主机 IP 或名称"; return; }
            Transport=mode; ConfigurationRevision++;
            endpoint="ws://"+(mode=="usb"?"127.0.0.1":host)+":"+number+"/input"+(mode=="wifi"?"?token="+Uri.EscapeDataString(code.Trim()):"");
            PlayerPrefs.SetString("rd.mode",mode); PlayerPrefs.SetString("rd.host",host); PlayerPrefs.SetString("rd.port",port);PlayerPrefs.SetString("rd.code",code.Trim());PlayerPrefs.Save();
            shortcuts.Reset();
            socket?.Abort(); commands.Clear(); pendingCommand=null; Host=null; ResetLatency(); nextConnect=0; connectRequested=true; Feedback="正在连接…";
        }
        public void Command(string action)
        {
            if(!Connected) { Feedback="请先连接主机"; return; }
            if(pendingCommand!=null && action!="stop") { Feedback="等待上一条操作";return; }
            pendingCommand=Guid.NewGuid().ToString("N"); commandDeadline=Time.unscaledTime+5;
            commands.Enqueue("{\"type\":\"command\",\"id\":\""+pendingCommand+"\",\"action\":\""+action+"\"}");
            Feedback="操作已发送，等待主机确认…";
        }
        private async Task Receive(ClientWebSocket client, CancellationToken token)
        {
            var buffer=new byte[32768];
            try {
                while(client.State==WebSocketState.Open && !token.IsCancellationRequested) {
                    int count=0; WebSocketReceiveResult result;
                    do { result=await client.ReceiveAsync(new ArraySegment<byte>(buffer,count,buffer.Length-count),token); if(result.MessageType==WebSocketMessageType.Close) { if(client==socket){Host=null;pendingCommand=null;Feedback="连接关闭："+result.CloseStatusDescription;} client.Abort(); return; } count+=result.Count; if(count>=buffer.Length)throw new Exception("主机消息过长"); } while(!result.EndOfMessage);
                    if(client!=socket) return;
                    var reply=JsonUtility.FromJson<HostStatus>(Encoding.UTF8.GetString(buffer,0,count));
                    if(reply.type=="status") { Host=reply; lastHostStatus=Time.realtimeSinceStartup; }
                    else if(reply.type=="latencyResult" && probePending && reply.probeId==probeId) {
                        RttMs=(float)((System.Diagnostics.Stopwatch.GetTimestamp()-probeStarted)*1000.0/System.Diagnostics.Stopwatch.Frequency);
                        lastLatencySample=Time.realtimeSinceStartup; probePending=false;
                    }
                    else if(reply.type=="commandResult" && reply.id==pendingCommand) { pendingCommand=null; Feedback=(reply.ok?"":"操作未完成：")+reply.message; }
                }
            } catch(Exception) { if(client==socket) Host=null; client.Abort(); }
        }
        private void ResetLatency() { RttMs=0; lastLatencySample=-100f; probePending=false; nextProbe=0; }
        private ClientWebSocket socket;
        private CancellationTokenSource lifetime;
        private Task operation;
        private float nextSend, nextConnect;
        private long sequence;

        [Serializable] public sealed class Hand
        {
            public bool connected, tracked, primary, secondary;
            public float[] position = new float[3], rotation = new float[] {0,0,0,1}, stick = new float[2];
            public float trigger, grip;
        }
        [Serializable] public sealed class Packet
        {
            public int version = 1;
            public string source = "quest";
            public string taskName;
            public long seq, timeMs;
            public bool focused, uiInteracting;
            public Hand left, right;
        }
        private void OnEnable() {
            lifetime = new CancellationTokenSource();
            UnityEngine.InputSystem.InputSystem.onDeviceChange += OnControllerChanged;
            TaskName=PlayerPrefs.GetString("rd.task","");
            if(Application.platform==RuntimePlatform.Android) {
                try {
                    using(var player=new AndroidJavaClass("com.unity3d.player.UnityPlayer"))
                    using(var activity=player.GetStatic<AndroidJavaObject>("currentActivity"))
                    using(var intent=activity.Call<AndroidJavaObject>("getIntent")) {
                        if(intent.Call<bool>("hasExtra","rd_mode")) {
                            foreach(var name in new[]{"mode","host","port","code"}) {
                                var value=intent.Call<string>("getStringExtra","rd_"+name);
                                if(value!=null)PlayerPrefs.SetString("rd."+name,value);
                                intent.Call<AndroidJavaObject>("removeExtra","rd_"+name)?.Dispose();
                            }
                        }
                    }
                } catch(Exception e) { Debug.LogWarning("RoboData connection setup: "+e.GetType().Name); }
            }
            Configure(PlayerPrefs.GetString("rd.mode","usb"),PlayerPrefs.GetString("rd.host",""),PlayerPrefs.GetString("rd.port","8766"),PlayerPrefs.GetString("rd.code",""));
        }
        private void OnDisable()
        {
            shortcuts.Reset();
            UnityEngine.InputSystem.InputSystem.onDeviceChange -= OnControllerChanged;
            lifetime.Cancel();
            socket?.Abort();
            socket?.Dispose();
            socket = null;
        }
        private void Update()
        {
            // Editor data is never presented as Quest hardware data.
            if (Application.platform != RuntimePlatform.Android) { Status = "USB bridge: Android only"; return; }
            ReadSetup();
            if(pendingCommand!=null && Time.unscaledTime>commandDeadline){pendingCommand=null;Feedback="主机操作回执超时，请确认状态后重试";}
            if (!Connected) Host=null;
            // Poll every frame, even while a send/connect is in progress. Do not
            // defer a blocked press until a host command or preparation finishes.
            var sim=Host?.simulation;
            var action=shortcuts.Read(ControllerInput.Read(XRNode.RightHand),
                Application.isFocused && !EditingText && HasFreshHostStatus && sim!=null && sim.online && !sim.preparing);
            if(action!=null)Command(action);
            if (!connectRequested) return;
            if (operation != null && !operation.IsCompleted) return;
            if (socket == null || socket.State != WebSocketState.Open)
            {
                if (Time.unscaledTime < nextConnect) return;
                nextConnect = Time.unscaledTime + 3f;
                operation = Connect(lifetime.Token);
                return;
            }
            if(commands.Count>0) { operation=Send(commands.Dequeue(),lifetime.Token);return; }
            // One lightweight probe per 500 ms; timed with a local monotonic clock.
            // Never derive latency from the periodic, possibly delayed status report.
            if(Time.realtimeSinceStartup>=nextProbe) {
                if(probePending && (System.Diagnostics.Stopwatch.GetTimestamp()-probeStarted)*1.0/System.Diagnostics.Stopwatch.Frequency<2) { }
                else {
                    probeId++; probePending=true; probeStarted=System.Diagnostics.Stopwatch.GetTimestamp();
                    nextProbe=Time.realtimeSinceStartup+.5f;
                    operation=Send("{\"type\":\"latencyProbe\",\"probeId\":"+probeId+"}",lifetime.Token);return;
                }
            }
            if (Time.unscaledTime < nextSend) return;
            nextSend = Time.unscaledTime + 1f / 30f;
            var p = new Packet { seq = sequence++, timeMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                uiInteracting=UiInteracting, taskName=TaskName, focused = Application.isFocused, left = Read(XRNode.LeftHand), right = Read(XRNode.RightHand) };
            operation = Send(JsonUtility.ToJson(p), lifetime.Token);
        }
        private async Task Connect(CancellationToken token)
        {
            socket?.Dispose();
            var client = new ClientWebSocket();
            socket = client;
            Status = "连接中…";
            try
            {
                using (var timeout = CancellationTokenSource.CreateLinkedTokenSource(token))
                {
                    timeout.CancelAfter(3000);
                    await client.ConnectAsync(new Uri(endpoint), timeout.Token);
                }
                ResetLatency();
                Status = "已连接";
                _ = Receive(client, token);
            }
            catch (Exception e) { Status = "连接重试 (" + e.GetType().Name + ")"; client.Abort(); }
        }
        private async Task Send(string json, CancellationToken token)
        {
            var client = socket;
            try
            {
                using (var timeout = CancellationTokenSource.CreateLinkedTokenSource(token))
                {
                    timeout.CancelAfter(1000);
                    await client.SendAsync(new ArraySegment<byte>(Encoding.UTF8.GetBytes(json)), WebSocketMessageType.Text, true, timeout.Token);
                }
                Status = "实时发送 · " + sequence + " 帧";
            }
            catch (Exception e) { Status = "连接重试 (" + e.GetType().Name + ")"; client.Abort(); }
        }
        private void OnControllerChanged(UnityEngine.InputSystem.InputDevice device, UnityEngine.InputSystem.InputDeviceChange change) {
            if(!(device is UnityEngine.InputSystem.XR.XRController))return;
            Debug.Log("[RoboData Input] device="+device.deviceId+" layout="+device.layout+" change="+change);
            if(device.added && device.enabled && (change==UnityEngine.InputSystem.InputDeviceChange.Added || change==UnityEngine.InputSystem.InputDeviceChange.Reconnected || change==UnityEngine.InputSystem.InputDeviceChange.Enabled))
                UnityEngine.InputSystem.InputSystem.TrySyncDevice(device);
        }
        private void OnApplicationFocus(bool focused) {
            shortcuts.Reset();
            if(!focused)return;
            foreach(var device in UnityEngine.InputSystem.InputSystem.devices)
                if(device is UnityEngine.InputSystem.XR.XRController && device.added && device.enabled)
                    UnityEngine.InputSystem.InputSystem.TrySyncDevice(device);
        }
        private void OnApplicationPause(bool paused) { if(paused)shortcuts.Reset(); }
        private readonly int[] lastInputStates={-1,-1}, lastInputDevices={-1,-1};
        private Hand Read(XRNode node) {
            var sample=ControllerInput.Read(node);int index=node==XRNode.LeftHand?0:1;
            int flags=(sample.connected?1:0)|(sample.tracked?2:0)|(sample.aimTracked?4:0)|(Application.isFocused?8:0);
            if(flags!=lastInputStates[index] || sample.deviceId!=lastInputDevices[index]) {
                Debug.Log($"[RoboData Input] side={node} device={sample.deviceId} connected={sample.connected} gripTracked={sample.tracked} aimTracked={sample.aimTracked} focus={Application.isFocused}");
                lastInputStates[index]=flags;lastInputDevices[index]=sample.deviceId;
            }
            return sample.Telemetry(Application.isFocused);
        }
    }
}
