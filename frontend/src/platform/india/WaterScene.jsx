import React, { useEffect, useRef } from 'react';

// Decorative water surface, not a representation of monitoring measurements.
export default function WaterScene() {
  const canvas = useRef(null);
  useEffect(() => {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (reduced.matches) return;
    let disposed = false, renderer, frame, geometry, material, observer;
    import('three').then(THREE => {
      if (disposed || !canvas.current) return;
      try {
        renderer = new THREE.WebGLRenderer({ canvas: canvas.current, alpha: true, antialias: false });
        renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(42, 2, 0.1, 30);
        camera.position.set(0, 2.8, 6.5);
        camera.lookAt(0, 0, 0);
        geometry = new THREE.PlaneGeometry(14, 6, 85, 32);
        geometry.rotateX(-Math.PI / 2);
        material = new THREE.MeshBasicMaterial({ color: '#c6d7f1', wireframe: true, transparent: true, opacity: 0.12 });
        const surface = new THREE.Mesh(geometry, material);
        scene.add(surface);
        const positions = geometry.attributes.position;
        const resize = () => { const bounds = canvas.current?.getBoundingClientRect(); if (!bounds) return; renderer.setSize(bounds.width, bounds.height, false); camera.aspect = bounds.width / Math.max(bounds.height, 1); camera.updateProjectionMatrix(); };
        observer = new ResizeObserver(resize); observer.observe(canvas.current); resize();
        let last = 0;
        const draw = now => {
          if (disposed) return;
          frame = requestAnimationFrame(draw);
          if (document.hidden || now - last < 42) return;
          last = now;
          for (let i = 0; i < positions.count; i++) positions.setY(i, Math.sin(positions.getX(i) * 0.7 + now * 0.00023) * 0.21 + Math.cos(positions.getZ(i) * 1.2 + now * 0.00018) * 0.12);
          positions.needsUpdate = true;
          renderer.render(scene, camera);
        };
        frame = requestAnimationFrame(draw);
      } catch { renderer?.dispose(); /* CSS gradient remains when WebGL is unavailable. */ }
    }).catch(() => {});
    return () => { disposed = true; cancelAnimationFrame(frame); observer?.disconnect(); geometry?.dispose(); material?.dispose(); renderer?.dispose(); };
  }, []);
  return <canvas className="in-water-scene" ref={canvas} aria-hidden="true"/>;
}
