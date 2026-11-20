import * as THREE from 'three';
import { Reflector } from '../vendor/Reflector.js';
import { OrbitControls } from '../vendor/OrbitControls.js';
import { CanvasRenderer } from './canvas-renderer.js';
import { createRenderer } from './renderer.js';
import { StudioError } from './errors.js';

export class Viewport {
  constructor(container) {
    THREE.Object3D.DEFAULT_UP.set(0, 0, 1);
    this.container = container;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color('#d5e1e8');
    this.scene.fog = new THREE.FogExp2('#c0c5c7', 0.035);
    this.camera = new THREE.PerspectiveCamera(36, 1, 0.01, 30);
    Object.assign(this, createRenderer({
      canvas: document.createElement('canvas'),
      createWebGL: (canvas, context) => new THREE.WebGLRenderer({ canvas, context, antialias: true, alpha: true }),
      createCanvas: () => new CanvasRenderer(),
    }));
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    if (!this.software) {
      this.renderer.shadowMap.enabled = true;
      this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    }
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.0;
    this.renderer.domElement.setAttribute('aria-label', 'S1 V1 三维模型，可旋转、缩放和平移');
    container.appendChild(this.renderer.domElement);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.09;
    this.controls.minDistance = 0.15;
    this.controls.maxDistance = 8;
    this.controls.maxPolarAngle = Math.PI * 0.97;
    this.controls.addEventListener('change', () => this.invalidate());
    this.scene.add(new THREE.HemisphereLight('#eef3f5', '#787b7d', 1.7));
    const key = new THREE.DirectionalLight('#fffaf2', 2.0);
    key.position.set(1, -1.6, 2.5);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    Object.assign(key.shadow.camera, { left: -1.2, right: 1.2, top: 1.2, bottom: -1.2, near: 0.1, far: 6 });
    key.shadow.bias = -0.0002;
    key.shadow.normalBias = 0.001;
    this.scene.add(key);
    const rim = new THREE.DirectionalLight('#e0e7ee', 0.9);
    rim.position.set(-1, 1.2, 1.6);
    this.scene.add(rim);
    // Planar reflection uses the same live scene and joint transforms, with a muted gray finish.
    if (!this.software) {
      const shader = {...Reflector.ReflectorShader,
        fragmentShader: Reflector.ReflectorShader.fragmentShader.replace(
          'vec4( blendOverlay( base.rgb, color ), 1.0 )', 'vec4( mix( color, base.rgb, 0.28 ), 1.0 )')};
      this.floor = new Reflector(new THREE.PlaneGeometry(200, 200), {
        color: '#a5abad', textureWidth: 1024, textureHeight: 1024, multisample: 0, clipBias: 0.003, shader,
      });
      this.floor.position.z = -0.054;
      this.scene.add(this.floor);
    }
    this.grid = new THREE.GridHelper(6, 60, '#7a858c', '#9aa4aa');
    this.grid.name = 'workspace-grid';
    this.grid.rotation.x = Math.PI / 2;
    this.grid.position.z = -0.053;
    this.grid.material.transparent = true;
    this.grid.material.opacity = 0.22;
    this.grid.visible = false;
    this.scene.add(this.grid);
    // Neutral mounting plate replaces the decorative blue pedestal; physics is unchanged.
    const pedestal = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.14, 0.012),
      new THREE.MeshPhongMaterial({color: '#a4a7a9', specular: '#8e969d', shininess: 65}));
    pedestal.position.z = -0.047;
    pedestal.receiveShadow = pedestal.castShadow = true;
    this.scene.add(pedestal);
    this.baseAxes = new THREE.AxesHelper(0.16);
    this.scene.add(this.baseAxes);
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(container);
    this.focus = new THREE.Vector3(0, 0, 0.25);
    this.distance = 1.55;
    this.setView('iso');
  }

  start() {
    this.renderer.setAnimationLoop(() => {
      try {
        this.controls.update();
        if (!this.software || this.dirty) {
          this.renderer.render(this.scene, this.camera);
          this.dirty = false;
        }
      } catch (cause) {
        this.stop();
        window.S1Startup.showError(new StudioError('RENDER_FRAME', '渲染帧执行失败', cause));
      }
    });
  }

  stop() {
    this.renderer.setAnimationLoop(null);
    this.resizeObserver.disconnect();
    this.controls.dispose();
    this.floor?.dispose();
  }

  resize() {
    const { clientWidth: width, clientHeight: height } = this.container;
    if (!width || !height) return;
    if (this.lastWidth === width && this.lastHeight === height) return;
    this.lastWidth = width;
    this.lastHeight = height;
    this.renderer.setSize(width, height);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.invalidate();
  }

  invalidate() { this.dirty = true; }

  attach(robot) {
    this.robot = robot;
    this.scene.add(robot.root);
    this.fit();
  }

  fit() {
    // Measure actual model meshes; exclude visual coordinate axes from framing.
    const bounds = new THREE.Box3();
    this.robot.root.traverse(object => {
      if (object.isMesh) bounds.expandByObject(object);
    });
    bounds.getCenter(this.focus);
    const size = bounds.getSize(new THREE.Vector3());
    const aspect = this.container.clientWidth / this.container.clientHeight;
    const verticalFov = THREE.MathUtils.degToRad(this.camera.fov);
    const horizontalFov = 2 * Math.atan(Math.tan(verticalFov / 2) * aspect);
    const radius = size.length() / 2;
    this.distance = radius / Math.sin(Math.min(verticalFov, horizontalFov) / 2) * 1.2;
    this.distance = Math.max(0.8, this.distance);
    this.setView(this.currentView || 'iso');
  }

  setView(name) {
    this.currentView = name;
    const direction = {
      iso: [1, -1.7, 0.4], front: [0, -1, 0.04], side: [1, 0, 0.04], top: [0, -0.001, 1],
    }[name];
    if (!direction) return;
    this.controls.target.copy(this.focus);
    this.camera.position.copy(this.focus).add(new THREE.Vector3(...direction).normalize().multiplyScalar(this.distance));
    this.camera.lookAt(this.focus);
    this.controls.update();
  }

  showAxes(visible) {
    this.baseAxes.visible = visible;
    if (this.robot) this.robot.tipAxes.visible = visible;
    this.invalidate();
  }
}
