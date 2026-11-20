export class RobotState extends EventTarget {
  constructor(model) {
    super();
    this.model = model;
    const joints = new Map();
    const visit = body => {
      if (body.joint) joints.set(body.joint.name, body.joint);
      body.children.forEach(visit);
    };
    model.bodies.forEach(visit);
    this.joints = model.armJoints.map(name => joints.get(name));
    if (this.joints.length !== 6 || this.joints.some(j => !j || j.type !== 'hinge')) {
      throw new Error('模型必须包含六个旋转关节');
    }
    this.positions = [...model.homeRadians];
    this.gripper = 40;
  }

  setJoint(index, radians) {
    if (!Number.isInteger(index) || !this.joints[index] || !Number.isFinite(radians)) return false;
    const [min, max] = this.joints[index].limits;
    this.positions[index] = Math.max(min, Math.min(max, radians));
    this.dispatchEvent(new Event('change'));
    return true;
  }

  setGripper(percent) {
    if (!Number.isFinite(percent)) return false;
    this.gripper = Math.max(0, Math.min(100, percent));
    this.dispatchEvent(new Event('change'));
    return true;
  }

  home() {
    this.positions = [...this.model.homeRadians];
    this.dispatchEvent(new Event('change'));
  }

  replace(positions, gripper) {
    if (positions.length !== 6 || !positions.every(Number.isFinite) || !Number.isFinite(gripper)) {
      throw new Error('后端返回了无效关节状态');
    }
    this.positions = [...positions];
    this.gripper = Math.max(0, Math.min(100, gripper));
    this.dispatchEvent(new Event('change'));
  }

  snapshot() {
    return { jointsRadians: [...this.positions], gripperPercent: this.gripper };
  }
}
