"""Explicit state snapshots and enable/disable, sharing the diagnostic CAN lock."""
import json
import time

from backend.hardware import ROOT, validate_detection
from backend.s1_can import S1Can
from backend.paths import data_dir


class HardwareOperations:
    def __init__(self, diagnostics, transport_factory=None, audit_path=None):
        self.diagnostics=diagnostics
        self.transport_factory=transport_factory or S1Can
        self.audit_path=audit_path or data_dir()/'audit/hardware-operations.jsonl'
        self.latest={}

    def _validate(self,value,action):
        if not isinstance(value,dict):raise ValueError('操作参数无效')
        config=validate_detection(value.get('config'))
        arm_id=value.get('armId')
        if arm_id not in ('A','B') or (config['layout']=='single' and arm_id=='B'):
            raise ValueError('请选择当前模式下的机械臂 A / B')
        if action=='enable' and value.get('confirmed') is not True:
            raise ValueError('使能前请确认现场和目标机械臂')
        arm=config['arms'][0 if arm_id=='A' else 1]
        return config,arm

    @staticmethod
    def _key(arm):
        return json.dumps(arm,sort_keys=True)

    def _check_interface(self,arm):
        info=next((i for i in self.diagnostics.interface_reader() if i['device']==arm['device']),None)
        if not info:raise ValueError('未找到接口 '+arm['device'])
        if not info['up']:raise ValueError('接口未启动：'+arm['device'])
        if info['busState'] in ('BUS-OFF','STOPPED','SLEEPING'):raise ValueError('总线异常：'+info['busState'])
        if arm['bitrate'] is not None and arm['bitrate']!=info['bitrate']:
            raise ValueError('配置速率与接口实际速率不一致，请先修正配置')

    def _audit(self,result):
        try:
            self.audit_path.parent.mkdir(parents=True,exist_ok=True)
            with self.audit_path.open('a') as log:
                log.write(json.dumps(result,ensure_ascii=False,allow_nan=False)+'\n')
            return True
        except OSError:
            return False

    def operate(self,action,value):
        if action not in ('read','enable','disable'):raise ValueError('不支持的真机操作')
        config,arm=self._validate(value,action)
        key=self._key(arm)
        nodes=list(range(1,8 if arm['endEffector']=='gripper' else 7))
        with self.diagnostics.exclusive():
            self._check_interface(arm)
            if action=='enable':
                previous=self.latest.get(key)
                if not previous or time.monotonic()-previous[0]>10 or not previous[1]['complete']:
                    raise ValueError('请先读取当前机械臂的完整状态，再在 10 秒内使能')
            transport=self.transport_factory(arm['device'])
            sent=[];send_error=None;command_attempted=False
            try:
                if action=='enable':
                    samples=transport.read(nodes,min(config['timeoutMs'],2000))
                    if len(samples)!=len(nodes) or any(s['fault'] or not s['positionValid'] for s in samples):
                        self.latest.pop(key,None)
                        raise ValueError('使能前复查未通过：有节点无响应、电机故障或角度异常，请重新读取状态')
                    # Only enable nodes currently disabled; never write target positions.
                    command_attempted=True
                    sent,send_error=transport.command([s['node'] for s in samples if not s['enabled']],action)
                elif action=='disable':
                    # Always attempt every configured node; no prior read or enable receipt required.
                    command_attempted=True
                    sent,send_error=transport.command(nodes,action)
                samples=transport.read(nodes,min(config['timeoutMs'],2000))
            except Exception as error:
                self.latest.pop(key,None)
                if command_attempted:
                    self._audit(dict(action=action,armId=arm['id'],device=arm['device'],verified=False,
                        message='指令后通信中断，结果未知：'+str(error),sentNodes=sent,sampledAtMs=int(time.time()*1000)))
                    raise OSError('指令后通信中断，电机状态未知；请重新读取：'+str(error)) from error
                raise
            finally:
                transport.close()
            responding={s['node'] for s in samples}
            missing=sorted(set(nodes)-responding)
            complete=not missing
            verified=complete and not send_error and (action=='read' or all(
                not s['fault'] and s['enabled']==(action=='enable') for s in samples))
            result=dict(config=config,armId=arm['id'],device=arm['device'],action=action,
                samples=samples,missingNodes=missing,complete=complete,verified=verified,
                sentNodes=sent,sendError=send_error,sampledAtMs=int(time.time()*1000),
                motionExecutionAvailable=False)
            result['message']=('状态读取完成' if complete else '状态不完整，缺少节点：'+', '.join(map(str,missing))) if action=='read' else (
                ('全部节点已确认使能' if action=='enable' else '全部节点已确认失能') if verified else
                '指令执行结果未完全确认，请查看节点反馈；不能视为全部成功')
            self.latest[key]=(time.monotonic(),result)
            if action!='read':
                if not self._audit(result):
                    result['message']+='；操作日志写入失败'
            return result
