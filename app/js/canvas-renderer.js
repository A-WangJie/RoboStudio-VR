// CPU fallback for Linux browser hosts without a working WebGL context.
// Uses the same Three.js scene graph and joint transforms as the WebGL renderer.
import * as THREE from 'three';

export class CanvasRenderer {
  constructor() {
    this.domElement = document.createElement('canvas');
    this.context = this.domElement.getContext('2d', { alpha: true });
    if (!this.context) throw new Error('浏览器不支持 Canvas 渲染');
    this.pixelRatio = 1;
    this.cache = new WeakMap();
  }
  setPixelRatio(value) { this.pixelRatio = Math.min(value, 1.5); }
  setSize(width, height) {
    this.width = width;
    this.height = height;
    this.domElement.width = width * this.pixelRatio;
    this.domElement.height = height * this.pixelRatio;
    this.domElement.style.width = `${width}px`;
    this.domElement.style.height = `${height}px`;
  }
  setAnimationLoop(callback) {
    cancelAnimationFrame(this.frame);
    this.callback = callback;
    if (!callback) return;
    const frame = () => {
      callback();
      if (this.callback === callback) this.frame = requestAnimationFrame(frame);
    };
    this.frame = requestAnimationFrame(frame);
  }
  triangles(geometry) {
    if (this.cache.has(geometry)) return this.cache.get(geometry);
    const position = geometry.getAttribute('position');
    const index = geometry.index;
    const triangles = [];
    const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
    for (let i = 0; i < (index ? index.count : position.count); i += 3) {
      a.fromBufferAttribute(position, index ? index.getX(i) : i);
      b.fromBufferAttribute(position, index ? index.getX(i + 1) : i + 1);
      c.fromBufferAttribute(position, index ? index.getX(i + 2) : i + 2);
      const normal = new THREE.Vector3().crossVectors(b.clone().sub(a), c.clone().sub(a)).normalize();
      triangles.push({ points: [a.clone(), b.clone(), c.clone()], normal });
    }
    this.cache.set(geometry, triangles);
    return triangles;
  }
  render(scene, camera) {
    if (!this.width || !this.height) return;
    const ctx = this.context;
    ctx.setTransform(this.pixelRatio, 0, 0, this.pixelRatio, 0, 0);
    ctx.clearRect(0, 0, this.width, this.height);
    const background = ctx.createLinearGradient(0, 0, 0, this.height);
    background.addColorStop(0, '#d5e1e8'); background.addColorStop(.45, '#c8ced1'); background.addColorStop(1, '#aeb5b9');
    ctx.fillStyle = background; ctx.fillRect(0, 0, this.width, this.height);
    scene.updateMatrixWorld(true);
    camera.updateMatrixWorld(true);
    const viewProjection = new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
    const project = vector => {
      const p = new THREE.Vector4(vector.x, vector.y, vector.z, 1).applyMatrix4(viewProjection);
      if (p.w <= camera.near) return null;
      return [(p.x / p.w + 1) * this.width / 2, (1 - p.y / p.w) * this.height / 2, p.z / p.w];
    };
    const line = (a, b, color, width = 1) => {
      const p = project(a), q = project(b);
      if (!p || !q) return;
      ctx.beginPath(); ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]);
      ctx.strokeStyle = color; ctx.lineWidth = width; ctx.stroke();
    };
    if (scene.getObjectByName('workspace-grid')?.visible) {
      for (let i = -25; i <= 25; i++) {
        const distance = i / 10;
        const color = i === 0 ? '#4b617765' : '#42556b45';
        line(new THREE.Vector3(-2.5, distance, -0.053), new THREE.Vector3(2.5, distance, -0.053), color);
        line(new THREE.Vector3(distance, -2.5, -0.053), new THREE.Vector3(distance, 2.5, -0.053), color);
      }
    }
    const faces = [];
    const light = new THREE.Vector3(1, -1.6, 2.5).normalize();
    const rim = new THREE.Vector3(-1, 1.2, 1.6).normalize();
    scene.traverseVisible(object => {
      if (!object.isMesh || object.userData.softwareSkip || !object.material.visible || object.material.opacity === 0) return;
      const normalMatrix = new THREE.Matrix3().getNormalMatrix(object.matrixWorld);
      const base = object.material.color.clone().convertLinearToSRGB();
      for (const triangle of this.triangles(object.geometry)) {
        const points = triangle.points.map(point => project(point.clone().applyMatrix4(object.matrixWorld)));
        if (points.some(p => !p)) continue;
        const [a, b, c] = points;
        const area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
        if (area >= -0.015) continue;
        if (points.every(p => p[0] < 0) || points.every(p => p[0] > this.width) ||
            points.every(p => p[1] < 0) || points.every(p => p[1] > this.height)) continue;
        const normal = triangle.normal.clone().applyMatrix3(normalMatrix).normalize();
        const intensity = 0.38 + Math.max(0, normal.dot(light)) * 0.5 + Math.max(0, normal.dot(rim)) * 0.2;
        const color = `rgb(${Math.min(255, base.r * intensity * 255) | 0},${Math.min(255, base.g * intensity * 255) | 0},${Math.min(255, base.b * intensity * 255) | 0})`;
        faces.push({ points, depth: (a[2] + b[2] + c[2]) / 3, color });
      }
    });
    faces.sort((a, b) => b.depth - a.depth);
    for (const face of faces) {
      const [a, b, c] = face.points;
      ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.lineTo(c[0], c[1]); ctx.closePath();
      ctx.fillStyle = face.color;
      ctx.fill();
      // Cover subpixel seams between adjacent STL triangles.
      ctx.strokeStyle = face.color;
      ctx.lineWidth = 0.35;
      ctx.stroke();
    }
    scene.traverseVisible(object => {
      if (object.type !== 'AxesHelper') return;
      const origin = new THREE.Vector3().applyMatrix4(object.matrixWorld);
      const position = object.geometry.getAttribute('position');
      ['#ef8d89', '#88d6a5', '#86b9fb'].forEach((color, index) => {
        const endpoint = new THREE.Vector3().fromBufferAttribute(position, index * 2 + 1).applyMatrix4(object.matrixWorld);
        line(origin, endpoint, color, 2);
      });
    });
  }
}
