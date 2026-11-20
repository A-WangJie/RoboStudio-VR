import * as THREE from 'three';

const SCALE_KEY = 'robostudio.mouse-follow-scale.v1';
const normalizeScale = value => Number.isFinite(value) && value >= 5 && value <= 100 ? Math.round(value / 5) * 5 : 30;

// Pointer positions map to a camera-facing plane through the current TCP.
export class MouseFollow {
  constructor(session) {
    this.session = session;
    this.viewport = session.viewport;
    this.canvas = this.viewport.renderer.domElement;
    this.ray = new THREE.Raycaster();
    this.gesture = null;
    const scaleInput = document.querySelector('#follow-scale');
    let savedScale = 30;
    try {savedScale = Number(localStorage.getItem(SCALE_KEY));} catch { /* Use the default if local storage is unavailable. */ }
    this.scalePercent = normalizeScale(savedScale);
    const showScale = () => {
      scaleInput.value = this.scalePercent;
      document.querySelector('#follow-scale-value').textContent = `${this.scalePercent}%`;
      scaleInput.setAttribute('aria-valuetext', `${this.scalePercent}%`);
    };
    showScale();
    scaleInput.addEventListener('input', () => {
      // Changing gain ends the old gesture so its accumulated offset cannot jump.
      this.stop(true);
      this.scalePercent = normalizeScale(scaleInput.valueAsNumber);
      showScale();
      try {localStorage.setItem(SCALE_KEY, String(this.scalePercent));} catch { /* The current session still uses the selected scale. */ }
    });
    const capture = {capture: true};
    this.canvas.addEventListener('pointerdown', event => this.down(event), capture);
    this.canvas.addEventListener('pointermove', event => this.move(event), capture);
    this.canvas.addEventListener('pointerup', event => this.up(event), capture);
    this.canvas.addEventListener('pointercancel', () => this.stop(true), capture);
    this.canvas.addEventListener('lostpointercapture', () => this.stop(true), capture);
    this.canvas.addEventListener('pointerleave', () => this.stop(true), capture);
    this.canvas.addEventListener('wheel', event => this.wheel(event), {capture: true, passive: false});
    document.addEventListener('pointerdown', event => {
      if (event.target !== this.canvas) this.stop(true);
    }, capture);
    document.addEventListener('keydown', event => {if(event.key === 'Escape') this.stop(true);});
    window.addEventListener('blur', () => this.stop(true));
    document.addEventListener('visibilitychange', () => {if(document.hidden) this.stop(true);});
  }

  enabled() {
    return this.session.ready && !this.viewport.software &&
      document.querySelector('#drag-toggle').getAttribute('aria-pressed') === 'true';
  }

  followingMode() {return this.enabled() && document.querySelector('#drag-mode').value === 'follow';}

  update() {
    this.stop(true);
    const active = this.enabled(), follow = this.followingMode();
    this.session.drag.enabled = false;
    this.session.drag.dragging = false;
    this.session.drag.axis = null;
    if (active && this.previousZoom === undefined) {
      this.previousZoom = this.viewport.controls.enableZoom;
      this.viewport.controls.enableZoom = false;
    } else if (!active && this.previousZoom !== undefined) {
      this.viewport.controls.enableZoom = this.previousZoom;
      this.previousZoom = undefined;
    }
    document.querySelector('#follow-options').hidden = document.querySelector('#drag-mode').value !== 'follow';
    this.session.drag.enabled = active && !follow;
    if (active && !follow) {
      this.session.drag.setMode(document.querySelector('#drag-mode').value);
      this.session.drag.attach(this.session.target);
    } else this.session.drag.detach();
    this.session.helper.visible = active && !follow;
    this.session.marker.visible = active;
    this.status();
    this.viewport.invalidate();
  }

  hit(event, plane) {
    const rect = this.canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    this.viewport.camera.updateMatrixWorld();
    this.ray.setFromCamera(new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1,
      1 - (event.clientY - rect.top) / rect.height * 2), this.viewport.camera);
    return this.ray.ray.intersectPlane(plane, new THREE.Vector3());
  }

  consume(event) {event.preventDefault();event.stopImmediatePropagation();}

  down(event) {
    if (!this.followingMode() || this.session.stopPending || event.pointerType !== 'mouse') return;
    if (event.button !== 0) {this.stop(true);return;}
    this.consume(event);
    if (this.gesture) {this.stop(true);return;}
    this.session.syncTarget();
    const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(
      this.viewport.camera.getWorldDirection(new THREE.Vector3()), this.session.target.position);
    const start = this.hit(event, plane);
    if (!start) return;
    const continuous = document.querySelector('#follow-behavior').value === 'continuous';
    this.gesture = {plane, start, scale: this.scalePercent / 100, target: this.session.target.position.clone(),
      pointerId: event.pointerId, continuous, orbitEnabled: this.viewport.controls.enabled};
    this.viewport.controls.enabled = false;
    // Hold mode captures the pointer until release; continuous mode tracks hover.
    if (!continuous) {
      try {this.canvas.setPointerCapture(event.pointerId);} catch { /* Synthetic QA pointers have no native capture. */ }
    }
    this.status();
  }

  move(event) {
    const gesture = this.gesture;
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    this.consume(event);
    if (!gesture.continuous && !(event.buttons & 1)) {this.stop(true);return;}
    const rect = this.canvas.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) {this.stop(true);return;}
    const hit = this.hit(event, gesture.plane);
    if (!hit) return;
    this.session.target.position.copy(gesture.target).addScaledVector(hit.sub(gesture.start), gesture.scale);
    this.session.writePose(this.session.target.position.toArray(), this.session.target.quaternion.toArray());
    this.session.queuePose();
    this.viewport.invalidate();
  }

  up(event) {
    if (!this.gesture || event.pointerId !== this.gesture.pointerId || event.button !== 0) return;
    this.consume(event);
    if (!this.gesture.continuous) this.stop(false);
  }

  stop(discard = false) {
    const gesture = this.gesture;
    this.gesture = null;
    if (gesture) {
      if(this.session.hardware?.active)this.session.hardware.hold();
      this.viewport.controls.enabled = gesture.orbitEnabled;
      if (discard && this.session.pending?.type === 'pose') {
        this.session.pending = null;
        clearTimeout(this.session.flushTimer);
        this.session.flushTimer = null;
      }
      try {
        if (this.canvas.hasPointerCapture(gesture.pointerId)) this.canvas.releasePointerCapture(gesture.pointerId);
      } catch { /* Pointer may already have been released by the browser. */ }
    }
    this.status();
  }

  status() {
    const active = this.followingMode();
    this.canvas.style.cursor = this.gesture ? 'grabbing' : active ? 'crosshair' : '';
    this.canvas.dataset.mouseFollow = this.gesture ? (this.gesture.continuous ? 'continuous' : 'hold') : 'idle';
    const status = document.querySelector('#follow-state');
    if (status) status.textContent = this.gesture ? '长跟随中 · Esc 停止' : active ? '长跟随待开始' : '长跟随未开启';
  }

  wheel(event) {
    if (!this.enabled() || !Number.isFinite(event.deltaY) || !event.deltaY) return;
    this.consume(event);
    const pixels = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? this.canvas.clientHeight : 1);
    const current = this.session.desiredGripper ?? this.session.snapshot.target_gripper;
    this.session.gripper(current - THREE.MathUtils.clamp(pixels, -100, 100) * .05);
  }
}
