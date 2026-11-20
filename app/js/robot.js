import * as THREE from 'three';
import { STLLoader } from '../vendor/STLLoader.js';
import { during } from './errors.js';

export class RobotModel {
  constructor(specification) {
    this.specification = specification;
    this.root = new THREE.Group();
    this.root.name = 'S1 V1';
    this.bodies = new Map();
    this.joints = new Map();
    this.geometry = new Map();
  }

  async load(baseURL) {
    const loader = new STLLoader();
    await Promise.all(Object.entries(this.specification.assets).map(async ([name, asset]) => {
      const url = new URL(asset.file, baseURL).href;
      const data = await during('MODEL_ASSET', `读取网格 ${name}：${url}`, async () => {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status} ${response.statusText}: ${url}`);
        return response.arrayBuffer();
      });
      const geometry = await during('MODEL_PARSE', `解析 STL ${name}：${url}`, () => {
        const parsed = loader.parse(data);
        const positions = parsed.getAttribute('position');
        if (!positions || positions.count < 3 || positions.count % 3 !== 0 ||
            positions.array.some(value => !Number.isFinite(value))) {
          throw new Error('STL 不包含有效的三角形顶点');
        }
        parsed.computeVertexNormals();
        parsed.computeBoundingBox();
        return parsed;
      });
      this.geometry.set(name, geometry);
    }));
    const build = (spec, parent) => {
      const origin = new THREE.Group();
      origin.name = spec.name;
      origin.position.fromArray(spec.position);
      const [w, x, y, z] = spec.quaternionWXYZ;
      origin.quaternion.set(x, y, z, w).normalize();
      parent.add(origin);
      let content = origin;
      if (spec.joint) {
        const pivot = new THREE.Group();
        pivot.position.fromArray(spec.joint.position);
        origin.add(pivot);
        content = new THREE.Group();
        content.position.fromArray(spec.joint.position).negate();
        pivot.add(content);
        this.joints.set(spec.joint.name, { pivot, spec: spec.joint,
          axis: new THREE.Vector3().fromArray(spec.joint.axis).normalize(),
          position: pivot.position.clone() });
      }
      this.bodies.set(spec.name, content);
      for (const visual of spec.visuals) {
        const graphite = ['2_Link', '3_Link', '4_Link'].includes(visual.mesh);
        const finger = visual.mesh.startsWith('7_');
        const material = new THREE.MeshPhongMaterial({
          color: finger ? '#666b70' : graphite ? '#59616e' : '#a3a6a8',
          specular: graphite ? '#77818f' : '#a6adb4', shininess: graphite ? 55 : 85,
        });
        const mesh = new THREE.Mesh(this.geometry.get(visual.mesh), material);
        mesh.name = visual.mesh;
        mesh.position.fromArray(visual.position);
        mesh.castShadow = mesh.receiveShadow = true;
        content.add(mesh);
      }
      spec.children.forEach(child => build(child, content));
    };
    this.specification.bodies.forEach(body => build(body, this.root));
    this.tip = new THREE.Object3D();
    this.tip.position.fromArray(this.specification.tip.position);
    this.bodies.get(this.specification.tip.body).add(this.tip);
    this.tipAxes = new THREE.AxesHelper(0.075);
    this.tipAxes.material.depthTest = false;
    this.tipAxes.renderOrder = 10;
    this.tip.add(this.tipAxes);
    return this;
  }

  setJoint(name, value) {
    const joint = this.joints.get(name);
    if (joint.spec.type === 'slide') {
      joint.pivot.position.copy(joint.position).addScaledVector(joint.axis, value);
    } else {
      joint.pivot.quaternion.setFromAxisAngle(joint.axis, value);
    }
  }

  apply(state) {
    this.specification.armJoints.forEach((name, i) => this.setJoint(name, state.positions[i]));
    const travel = state.gripper / 100 * this.specification.gripperTravelMeters;
    this.specification.gripperJoints.forEach(name => this.setJoint(name, travel));
    this.root.updateMatrixWorld(true);
  }

  tipPosition() {
    const point = this.tip.getWorldPosition(new THREE.Vector3());
    return this.root.worldToLocal(point);
  }

  highlightContacts(contacts) {
    const names = new Set(contacts.flatMap(contact => contact.pair));
    for (const [name, body] of this.bodies) {
      for (const mesh of body.children.filter(child => child.isMesh)) {
        if (!mesh.userData.originalColor) mesh.userData.originalColor = mesh.material.color.clone();
        if (names.has(name)) mesh.material.color.set('#e96d62');
        else mesh.material.color.copy(mesh.userData.originalColor);
      }
    }
  }

  bodyTransforms() {
    this.root.updateMatrixWorld(true);
    return Object.fromEntries([...this.bodies].map(([name, body]) => [name, {
      position: body.getWorldPosition(new THREE.Vector3()).toArray(),
      quaternion: body.getWorldQuaternion(new THREE.Quaternion()).toArray(),
    }]));
  }
}
